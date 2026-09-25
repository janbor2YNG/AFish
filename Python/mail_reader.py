"""Read the support/report inbox and mark forwarded/reported phishing mails.

When a teacher forwards/reports a simulation mail, the body still contains the
discreet reference marker from the template footer (e.g. ``Ref: TRX-3``).
Matching that wave number to the sender's address marks the matching ``events``
row as ``reported`` (= recognised the phishing simulation).
"""

import os
import re
import sys
import email
import imaplib
import sqlite3
from datetime import datetime, timedelta
from email.utils import parseaddr
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402

MARKER_RE = re.compile(r"\bTRX-(\d+)\b", re.IGNORECASE)


def get_db_path(campaign_id=None) -> Path:
    """Return the path of a specific campaign DB, or the latest one."""
    folder = Path(cfg.DATABASES_DIR)
    if campaign_id is not None:
        path = folder / f"campaign{campaign_id}.db"
        if not path.exists():
            raise FileNotFoundError(f"campaign{campaign_id}.db not found")
        return path
    dbs = sorted(
        folder.glob("campaign*.db"),
        key=lambda p: int(re.search(r"\d+", p.stem).group()),
    )
    if not dbs:
        raise FileNotFoundError("No campaign*.db database found")
    return dbs[-1]


def to_imap_date(date_str, offset_days=0):
    """Convert 'DD.MM.YYYY' to the IMAP date format 'DD-Mon-YYYY', optionally
    shifted by ``offset_days`` (used to build an inclusive-enough search window)."""
    date = datetime.strptime(date_str, "%d.%m.%Y") + timedelta(days=offset_days)
    return date.strftime("%d-%b-%Y")


def _extract_body(msg):
    """Return the message's text content, searched for the TRX marker.

    Prefers text/plain parts, but falls back to text/html: some mail clients
    forward a message as HTML-only (no text/plain alternative at all), and
    the marker text is present in the HTML source either way since it is
    plain text inside the template, not an image or styled element.
    """
    if not msg.is_multipart():
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="replace")

    plain, html = "", ""
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        charset = part.get_content_charset() or "utf-8"
        text = part.get_payload(decode=True).decode(charset, errors="replace")
        if content_type == "text/plain":
            plain += text
        else:
            html += text
    return plain or html


def mark_reported(db_path, sender_email, wave_nr, when):
    """Mark the (user, wave) event as reported. Returns True if a row was updated.

    Never overwrites an event that is already reported, so the *first* report
    timestamp is kept even if the inbox is scanned again later (e.g. by the
    periodic background check and then again via the manual "check" button).
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (sender_email,))
        user = cursor.fetchone()
        if not user:
            return False
        cursor.execute(
            """UPDATE events SET status = ?, reported_at = ?
               WHERE user_id = ? AND wave = ? AND status != ?""",
            (cfg.STATUS_REPORTED, when, user[0], wave_nr, cfg.STATUS_REPORTED),
        )
        return cursor.rowcount > 0


def _campaign_window(db_path):
    """Read the campaign's own start/end dates from its campaign_meta row.

    Using the campaign's own stored dates (rather than whatever config file
    happens to be "active" right now) matters: the active config can change
    between when a campaign was created and when its inbox is checked, e.g.
    after uploading a new YAML for a later campaign. Using the wrong dates
    here does not raise an error - it just silently narrows (or shifts) the
    IMAP search window, so reports can go undetected with no visible failure.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT start_date, end_date FROM campaign_meta WHERE id = 1").fetchone()
    return (row["start_date"], row["end_date"]) if row else (None, None)


def check_responses(campaign_id=None, settings=None, logger=print):
    """Scan the report inbox for forwarded mails and update the campaign DB.

    Returns the number of events marked as ``reported``. Skipped in dry-run mode.
    """
    settings = settings or cfg.get_settings()
    if settings.get("dry_run", True):
        logger("[DRY-RUN] Skipping IMAP inbox check (enable real mode in settings).")
        return 0

    db_path = get_db_path(campaign_id)
    start, end = _campaign_window(db_path)

    mail = imaplib.IMAP4_SSL(settings["imap_server"])
    mail.login(settings["sender_email"], settings["sender_password"])
    mail.select("inbox")

    if start and end:
        # A day of slack on both sides: IMAP's BEFORE is exclusive of the
        # given date, so without the +1 a report arriving ON the campaign's
        # own end date (very likely for a same-day test) would silently be
        # excluded from the search entirely. The -1 covers timezone/clock
        # differences between this machine and the mail server.
        since = to_imap_date(start, offset_days=-1)
        before = to_imap_date(end, offset_days=1)
        search_query = f'(SINCE "{since}" BEFORE "{before}")'
    else:
        search_query = "ALL"
    status, messages = mail.search(None, search_query)
    email_ids = messages[0].split()
    logger(f"[check_responses] campaign {campaign_id}: scanning {len(email_ids)} message(s) "
           f"with query {search_query!r}")

    updated = 0
    for e_id in email_ids:
        status, msg_data = mail.fetch(e_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        sender_email = parseaddr(msg["From"])[1]
        body = _extract_body(msg)

        match = MARKER_RE.search(body)
        if not match:
            continue

        wave_nr = int(match.group(1))
        now = datetime.now().isoformat(timespec="seconds")
        if mark_reported(db_path, sender_email, wave_nr, now):
            updated += 1
            logger(f"{sender_email} -> wave {wave_nr} = {cfg.STATUS_REPORTED}")
        else:
            logger(f"[check_responses] marker TRX-{wave_nr} from {sender_email} found but no "
                   f"matching (user, wave) event in campaign {campaign_id} - ignored")

    mail.logout()
    return updated


if __name__ == "__main__":
    check_responses()
