"""Read the support inbox and mark forwarded/reported phishing mails.

REFACTORED from the former ``MailRead.py``: module-level code and hard-coded
credentials removed; the logic is wrapped in ``check_responses()``. When a
teacher forwards/reports a simulation mail, the body still contains the
``mh<wave>`` marker; matching that to the sender marks ``mail_<wave>`` as
``reported`` (= recognised the phishing) for that user.
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


def check_responses(campaign_id=None, settings=None, logger=print):
    """Scan the inbox for reported mails and update the campaign DB.

    Returns the number of users marked as ``reported``. Skipped in dry-run mode.
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

        match = re.search(r"\bmh(\d+)\b", body, re.IGNORECASE)
        if not match:
            continue

        wave_nr = int(match.group(1))
        column = f"mail_{wave_nr}"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            if column not in columns:
                continue
            cursor.execute("SELECT id FROM users WHERE email = ?", (sender_email,))
            user = cursor.fetchone()
            if not user:
                continue
            cursor.execute(
                f"UPDATE users SET {column} = ? WHERE id = ?",
                (cfg.STATUS_REPORTED, user[0]),
            )
            updated += 1
            logger(f"{sender_email} -> {column} = {cfg.STATUS_REPORTED}")

    mail.logout()
    return updated


if __name__ == "__main__":
    check_responses()
