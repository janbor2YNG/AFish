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
from datetime import datetime
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


def to_imap_date(date_str):
    """Convert 'DD.MM.YYYY' to the IMAP date format 'DD-Mon-YYYY'."""
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%d-%b-%Y")


def _extract_body(msg):
    if msg.is_multipart():
        body = ""
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                body += part.get_payload(decode=True).decode(charset, errors="replace")
        return body
    charset = msg.get_content_charset() or "utf-8"
    return msg.get_payload(decode=True).decode(charset, errors="replace")


def mark_reported(db_path, sender_email, wave_nr, when):
    """Mark the (user, wave) event as reported. Returns True if a row was updated."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (sender_email,))
        user = cursor.fetchone()
        if not user:
            return False
        cursor.execute(
            """UPDATE events SET status = ?, reported_at = ?
               WHERE user_id = ? AND wave = ?""",
            (cfg.STATUS_REPORTED, when, user[0], wave_nr),
        )
        return cursor.rowcount > 0


def check_responses(campaign_id=None, settings=None, logger=print):
    """Scan the report inbox for forwarded mails and update the campaign DB.

    Returns the number of events marked as ``reported``. Skipped in dry-run mode.
    """
    settings = settings or cfg.get_settings()
    if settings.get("dry_run", True):
        logger("[DRY-RUN] Skipping IMAP inbox check (enable real mode in settings).")
        return 0

    db_path = get_db_path(campaign_id)
    config = cfg.load_config()
    start_date = to_imap_date(config["send"]["timeframe"]["start"])
    end_date = to_imap_date(config["send"]["timeframe"]["end"])

    mail = imaplib.IMAP4_SSL(settings["imap_server"])
    mail.login(settings["sender_email"], settings["sender_password"])
    mail.select("inbox")

    status, messages = mail.search(None, f'(SINCE "{start_date}" BEFORE "{end_date}")')
    email_ids = messages[0].split()

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

    mail.logout()
    return updated


if __name__ == "__main__":
    check_responses()
