"""Background campaign runner.

NEW module: drives a campaign from the web UI. Starting a campaign launches a
background thread that sends the waves that are *due* (according to the YAML
timeframe distribution) and keeps polling until the campaign is finished or
stopped. State is mirrored into the ``campaign_meta`` table so the dashboard can
display live progress, and survives even though the thread itself does not.
"""

import os
import sys
import threading
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402
import mail_sender            # noqa: E402
import mail_reader            # noqa: E402

# How long the runner sleeps between schedule checks, and between single waves.
POLL_INTERVAL_SECONDS = 30
WAVE_INTERVAL_SECONDS = 2

# Registry of running campaigns: campaign_id -> {"thread", "stop_event"}.
_runners = {}
_lock = threading.Lock()


def _db_path(campaign_id):
    return os.path.join(cfg.DATABASES_DIR, f"campaign{campaign_id}.db")


def _read_meta(campaign_id):
    path = _db_path(campaign_id)
    if not os.path.exists(path):
        return None
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM campaign_meta WHERE id = 1").fetchone()
    return dict(row) if row else None


def _update_meta(campaign_id, **fields):
    if not fields:
        return
    path = _db_path(campaign_id)
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with sqlite3.connect(path) as conn:
        conn.execute(f"UPDATE campaign_meta SET {assignments} WHERE id = 1", tuple(fields.values()))


def is_running(campaign_id):
    with _lock:
        runner = _runners.get(campaign_id)
        return bool(runner and runner["thread"].is_alive())


def get_status(campaign_id):
    """Return live status + progress for a campaign."""
    meta = _read_meta(campaign_id)
    if not meta:
        return None
    running = is_running(campaign_id)
    total = meta.get("total_emails") or 0
    sent = meta.get("sent_count") or 0
    return {
        "id": campaign_id,
        "name": meta.get("name"),
        "status": "running" if running else meta.get("status"),
        "running": running,
        "sent_count": sent,
        "total_emails": total,
        "progress": round(sent / total * 100) if total else 0,
        "start_date": meta.get("start_date"),
        "end_date": meta.get("end_date"),
    }


def _run_loop(campaign_id, stop_event):
    """Worker: send due waves until finished or stopped."""
    meta = _read_meta(campaign_id)
    if not meta:
        return
    config = cfg.load_config(meta.get("config_file"))
    settings = cfg.get_settings()
    total = meta.get("total_emails") or 0
    start = meta.get("start_date")
    end = meta.get("end_date")
    plan = mail_sender.build_distribution_plan(start, end, total)

    _update_meta(campaign_id, status="running")

    while not stop_event.is_set():
        meta = _read_meta(campaign_id)
        sent = meta.get("sent_count") or 0
        due = min(mail_sender.waves_due_by(plan), total)

        while sent < due and not stop_event.is_set():
            wave_id = sent + 1
            try:
                mail_sender.send_wave(wave_id, _db_path(campaign_id), config, settings)
            except Exception as exc:  # keep the runner alive on send errors
                print(f"[runner] campaign {campaign_id} wave {wave_id} error: {exc}")
            sent += 1
            _update_meta(campaign_id, sent_count=sent)
            stop_event.wait(WAVE_INTERVAL_SECONDS)

        # Pull in any reported mails (no-op in dry-run mode).
        try:
            mail_reader.check_responses(campaign_id, settings)
        except Exception as exc:
            print(f"[runner] campaign {campaign_id} inbox check error: {exc}")

        finished = sent >= total or (
            end and datetime.now().date() > datetime.strptime(end, "%d.%m.%Y").date()
        )
        if finished:
            _update_meta(campaign_id, status="finished")
            break

        stop_event.wait(POLL_INTERVAL_SECONDS)

    if stop_event.is_set():
        _update_meta(campaign_id, status="stopped")

    with _lock:
        _runners.pop(campaign_id, None)


def start_campaign(campaign_id):
    """Start (or resume) a campaign in the background. Returns True on start."""
    if _read_meta(campaign_id) is None:
        return False
    with _lock:
        existing = _runners.get(campaign_id)
        if existing and existing["thread"].is_alive():
            return False
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_run_loop, args=(campaign_id, stop_event), daemon=True
        )
        _runners[campaign_id] = {"thread": thread, "stop_event": stop_event}
        thread.start()
    return True


def stop_campaign(campaign_id):
    """Signal a running campaign to stop. Returns True if it was running."""
    with _lock:
        runner = _runners.get(campaign_id)
        if not runner:
            _update_meta(campaign_id, status="stopped")
            return False
        runner["stop_event"].set()
    return True
