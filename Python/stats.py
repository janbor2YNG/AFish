"""Shared statistics gathering for the dashboard API and the Excel export.

Both read the same ``events``/``users``/``campaign_meta`` tables so the numbers
shown on screen and the numbers in the exported Excel file always match.
"""

import os
import sys
import sqlite3
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402


def db_path_for(campaign_id):
    return os.path.join(cfg.DATABASES_DIR, f"campaign{campaign_id}.db")


def list_campaign_ids():
    folder = Path(cfg.DATABASES_DIR)
    if not folder.exists():
        return []
    ids = []
    for p in folder.glob("campaign*.db"):
        digits = "".join(ch for ch in p.stem if ch.isdigit())
        if digits:
            ids.append(int(digits))
    return sorted(ids)


def campaign_stats(campaign_id):
    """Return the full stats structure for one campaign, or None if it doesn't exist.

    Structure:
    {
      "meta": {...campaign_meta row...},
      "totals": {"sent": N, "clicked": N, "reported": N, "by_category": {cat: N, ...}},
      "click_rate": float 0..100, "report_rate": float 0..100,
      "users": [{"id","name","email","gruppe","sent","clicked","reported","repeat_fail"}...],
      "events": [{"user_name","user_email","wave","category","template",
                  "sender_name","sender_email","status","sent_at","clicked_at","reported_at"}...],
    }
    """
    path = db_path_for(campaign_id)
    if not os.path.exists(path):
        return None

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        meta = conn.execute("SELECT * FROM campaign_meta WHERE id = 1").fetchone()
        users = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
        events = conn.execute(
            """SELECT events.*, users.name AS user_name, users.email AS user_email
               FROM events JOIN users ON users.id = events.user_id
               ORDER BY events.sent_at"""
        ).fetchall()

    by_category = {}
    total_clicked = 0
    total_reported = 0
    per_user = {u["id"]: {
        "id": u["id"], "name": u["name"], "email": u["email"], "gruppe": u["gruppe"],
        "sent": 0, "clicked": 0, "reported": 0,
    } for u in users}

    event_list = []
    for e in events:
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1
        if e["status"] == cfg.STATUS_CLICKED:
            total_clicked += 1
        if e["status"] == cfg.STATUS_REPORTED:
            total_reported += 1
        row = per_user.get(e["user_id"])
        if row:
            row["sent"] += 1
            if e["status"] == cfg.STATUS_CLICKED:
                row["clicked"] += 1
            if e["status"] == cfg.STATUS_REPORTED:
                row["reported"] += 1
        event_list.append({
            "user_name": e["user_name"], "user_email": e["user_email"], "wave": e["wave"],
            "category": e["category"], "template": e["template"],
            "sender_name": e["sender_name"], "sender_email": e["sender_email"],
            "status": e["status"], "sent_at": e["sent_at"],
            "clicked_at": e["clicked_at"], "reported_at": e["reported_at"],
        })

    user_list = list(per_user.values())
    for row in user_list:
        row["repeat_fail"] = row["clicked"] >= 2

    total_sent = len(event_list)
    click_rate = round(total_clicked / total_sent * 100, 1) if total_sent else 0.0
    report_rate = round(total_reported / total_sent * 100, 1) if total_sent else 0.0

    return {
        "meta": dict(meta) if meta else {},
        "totals": {"sent": total_sent, "clicked": total_clicked, "reported": total_reported,
                    "by_category": by_category},
        "click_rate": click_rate,
        "report_rate": report_rate,
        "users": user_list,
        "events": event_list,
    }


def compare_campaigns():
    """Return click/report rates for every campaign, oldest first - used to show
    progress between training rounds."""
    result = []
    for cid in list_campaign_ids():
        stats = campaign_stats(cid)
        if not stats:
            continue
        result.append({
            "id": cid,
            "name": stats["meta"].get("name"),
            "created_at": stats["meta"].get("created_at"),
            "click_rate": stats["click_rate"],
            "report_rate": stats["report_rate"],
            "sent": stats["totals"]["sent"],
        })
    result.sort(key=lambda c: c["created_at"] or "")
    return result
