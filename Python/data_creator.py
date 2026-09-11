"""Create and populate a new campaign database.

Each campaign lives in its own ``Python/databases/campaign{N}.db`` containing:

* ``users``         - the imported recipients (name, email, optional group)
* ``events``         - one row per mail actually sent (wave, template, sender,
  status + timestamps) - this is what the Excel "Detaildaten" sheet is built from
* ``campaign_meta``  - a single metadata row (name, dates, status, progress)

Recipients are imported as-is from the CSV - no age/role/subject filtering.
Keep the imported list to what is really needed (name, email, optional group)
to minimise personal data, per the project's privacy requirement.
"""

import sqlite3
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402


def _next_db_path() -> Path:
    """Return the next free campaign{N}.db path."""
    folder = Path(cfg.DATABASES_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    counter = 1
    while (folder / f"campaign{counter}.db").exists():
        counter += 1
    return folder / f"campaign{counter}.db"


CREATE_USERS_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        gruppe TEXT
    )
"""

CREATE_EVENTS_SQL = f"""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        wave INTEGER NOT NULL,
        category TEXT NOT NULL,
        template TEXT NOT NULL,
        sender_name TEXT,
        sender_email TEXT,
        status TEXT NOT NULL DEFAULT '{cfg.STATUS_SENT}'
            CHECK(status IN ('{cfg.STATUS_SENT}', '{cfg.STATUS_CLICKED}', '{cfg.STATUS_REPORTED}')),
        token TEXT UNIQUE,
        sent_at TEXT,
        clicked_at TEXT,
        reported_at TEXT
    )
"""

CREATE_META_SQL = """
    CREATE TABLE IF NOT EXISTS campaign_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        name TEXT,
        description TEXT,
        config_file TEXT,
        start_date TEXT,
        end_date TEXT,
        total_waves INTEGER,
        status TEXT DEFAULT 'created',
        waves_sent INTEGER DEFAULT 0,
        created_at TEXT
    )
"""


def create_campaign_db(config: dict, config_name: str) -> Path:
    """Create a new campaign database from a parsed YAML config.

    Returns the path of the freshly created ``campaign{N}.db``.
    """
    total_waves = int(config["send"]["total_waves"])
    db_path = _next_db_path()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(CREATE_USERS_SQL)
        cursor.execute(CREATE_EVENTS_SQL)
        cursor.execute(CREATE_META_SQL)

        send = config.get("send", {})
        timeframe = send.get("timeframe", {})
        cursor.execute(
            """INSERT INTO campaign_meta
               (id, name, description, config_file, start_date, end_date,
                total_waves, status, waves_sent, created_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, 'created', 0, ?)""",
            (
                config.get("name", config_name),
                config.get("description", ""),
                config_name,
                timeframe.get("start", ""),
                timeframe.get("end", ""),
                total_waves,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        # --- Import recipients from the CSV, unfiltered ---------------------
        inserted = 0
        with open(cfg.CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or "").strip()
                email = (row.get("email") or "").strip()
                gruppe = (row.get("gruppe") or "").strip() or None
                if not email:
                    continue
                cursor.execute(
                    "INSERT OR IGNORE INTO users (name, email, gruppe) VALUES (?, ?, ?)",
                    (name, email, gruppe),
                )
                inserted += cursor.rowcount

    print(f"Created {db_path} with {inserted} recipients ({total_waves} waves).")
    return db_path


if __name__ == "__main__":
    # Manual run: build a campaign from the currently active config.
    create_campaign_db(cfg.load_config(), cfg.get_active_config_name())
