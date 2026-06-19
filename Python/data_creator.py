"""Create and populate a new campaign database.

REFACTORED: the former module-level script is now wrapped in the callable
``create_campaign_db()`` so the Flask app can trigger campaign creation from the
web UI. The original filtering logic (formerly ``user_erlaubt``) is preserved as
``user_allowed`` with identical behaviour.

Each campaign lives in its own ``Python/databases/campaign{N}.db`` containing:
* ``users``         – the filtered recipients + one ``mail_<n>`` column per wave
* ``campaign_meta`` – a single metadata row (name, dates, status, progress)
"""

import sqlite3
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Make the shared config_manager importable regardless of the working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402


def _next_db_path() -> Path:
    """Return the next free campaign{N}.db path (reuses original numbering)."""
    folder = Path(cfg.DATABASES_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    counter = 1
    while (folder / f"campaign{counter}.db").exists():
        counter += 1
    return folder / f"campaign{counter}.db"


def user_allowed(row, include_roles, exclude_roles, required_fach, min_alter):
    """Decide whether a CSV row matches the campaign target filter.

    (Unchanged logic, formerly ``user_erlaubt`` – just renamed to English and
    made parameter-driven so it no longer relies on module globals.)
    """
    role = (row.get("role") or "").strip()
    age_str = (row.get("age") or "0").strip()
    subjects = {(row.get("sub1") or "").strip(), (row.get("sub2") or "").strip()}

    try:
        age = int(age_str)
    except ValueError:
        return False

    if age < min_alter:
        return False
    if role in exclude_roles:
        return False
    if include_roles and role not in include_roles:
        return False
    if required_fach and not subjects.intersection(required_fach):
        return False
    return True


def create_campaign_db(config: dict, config_name: str) -> Path:
    """Create a new campaign database from a parsed YAML config.

    Returns the path of the freshly created ``campaign{N}.db``.
    """
    total_mails = int(config["send"]["total_emails"])
    db_path = _next_db_path()

    # Build the dynamic mail_<n> columns (one per wave) with English statuses.
    mail_columns = ""
    for i in range(1, total_mails + 1):
        mail_columns += (
            f"    mail_{i} TEXT DEFAULT '{cfg.STATUS_NO_RESPONSE}' "
            f"CHECK(mail_{i} IN "
            f"('{cfg.STATUS_REPORTED}', '{cfg.STATUS_CLICKED}', '{cfg.STATUS_NO_RESPONSE}')),\n"
        )
    mail_columns = mail_columns.rstrip(",\n")

    create_users_sql = f"""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            lastname TEXT,
            email TEXT,
        {mail_columns}
        )
    """

    # NEW: per-campaign metadata table (drives the dashboard + runner).
    create_meta_sql = """
        CREATE TABLE IF NOT EXISTS campaign_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT,
            description TEXT,
            config_file TEXT,
            start_date TEXT,
            end_date TEXT,
            total_emails INTEGER,
            status TEXT DEFAULT 'created',
            sent_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(create_users_sql)
        cursor.execute(create_meta_sql)

        send = config.get("send", {})
        timeframe = send.get("timeframe", {})
        cursor.execute(
            """INSERT INTO campaign_meta
               (id, name, description, config_file, start_date, end_date,
                total_emails, status, sent_count, created_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, 'created', 0, ?)""",
            (
                config.get("name", config_name),
                config.get("description", ""),
                config_name,
                timeframe.get("start", ""),
                timeframe.get("end", ""),
                total_mails,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        # --- Filter recipients from the CSV (same criteria as before) -------
        target = config.get("target", {}) or {}
        include_roles = target.get("include_role") or []
        exclude_roles = target.get("exclude_role") or []
        required_fach = target.get("fach") or []
        min_alter = target.get("min_alter") or 0

        recipients = []
        with open(cfg.CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if user_allowed(row, include_roles, exclude_roles, required_fach, min_alter):
                    recipients.append(row)

        inserted = 0
        for row in recipients:
            name = (row.get("name") or "").strip()
            lastname = (row.get("lastname") or "").strip()
            email = (row.get("email") or "").strip()
            if not email:
                continue
            cursor.execute(
                "INSERT INTO users (name, lastname, email) VALUES (?, ?, ?)",
                (name, lastname, email),
            )
            inserted += 1

    print(f"Created {db_path} with {inserted} recipients ({total_mails} mail waves).")
    return db_path


if __name__ == "__main__":
    # Manual run: build a campaign from the currently active config.
    create_campaign_db(cfg.load_config(), cfg.get_active_config_name())
