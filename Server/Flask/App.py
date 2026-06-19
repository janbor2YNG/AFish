"""AFish – central Flask application.

This is the single entry point that hosts the whole phishing-simulation tool:
admin authentication, the dashboard, all JSON APIs (campaigns, stats, users,
config, settings) and the public phishing-tracking endpoints.

REWORKED from the original App.py: the engine scripts in ``Python/`` are now
imported and driven from here, every dashboard control has a matching endpoint,
and the German status values were replaced by the English ones from
``config_manager``.
"""

import os
import sys
import csv
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask, request, jsonify, session, redirect,
    send_from_directory, url_for,
)

# Local (Server/Flask) + engine (Python/) imports.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)  # so config_manager resolves regardless of cwd
sys.path.insert(0, os.path.join(BASE_DIR, "..", "..", "Python"))

import config_manager as cfg          # noqa: E402
import data_creator                   # noqa: E402
import mail_reader                    # noqa: E402
import campaign_runner                # noqa: E402

HTML_DIR = os.path.join(cfg.REPO_ROOT, "UI", "HTML")

app = Flask(
    __name__,
    static_folder=os.path.join(cfg.REPO_ROOT, "UI"),
    static_url_path="/static",
)
app.secret_key = "afish-internal-secret"  # dev tool – plain session secret


# --- Authentication --------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Nicht angemeldet"}), 401
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET"])
def login_page():
    return send_from_directory(HTML_DIR, "login.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    password = data.get("password", "")
    if password == cfg.get_setting("admin_password"):
        session["logged_in"] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Falsches Passwort"}), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# --- Dashboard -------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    return send_from_directory(HTML_DIR, "dashboard.html")


# --- Public phishing tracking ---------------------------------------------
@app.route("/track")
def track():
    """Public landing page reached when a teacher clicks the phishing link.

    Serves a tiny page that runs the tracking script (records the click) and
    then forwards to the awareness page. No login required by design.
    """
    return (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
        "<title>Weiterleitung…</title></head><body>"
        "<script src='/fakeWebsiteBackend.js'></script>"
        "<p style='font-family:sans-serif'>Einen Moment bitte…</p>"
        "</body></html>"
    )


@app.route("/awareness")
def awareness():
    """Educational page shown after a simulated phishing link was clicked."""
    return (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
        "<title>Phishing-Simulation</title></head>"
        "<body style='font-family:sans-serif;max-width:640px;margin:60px auto;line-height:1.6'>"
        "<h1>Dies war eine Phishing-Simulation</h1>"
        "<p>Diese E-Mail war Teil einer Sensibilisierungs-Maßnahme Ihrer Schule. "
        "Echte Angreifer hätten an dieser Stelle versucht, Ihre Zugangsdaten zu "
        "stehlen. Bitte melden Sie verdächtige E-Mails künftig an Ihren "
        "IT-Sicherheitsbeauftragten.</p></body></html>"
    )


@app.route("/fakeWebsiteBackend.js")
def fake_website_backend():
    return send_from_directory(BASE_DIR, "fakeWebsiteBackend.js",
                               mimetype="application/javascript")


@app.route("/apply", methods=["POST"])
def apply():
    """Record a click on the phishing link as ``clicked`` (= failed)."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    wave_id = data.get("id")
    campaign_id = data.get("c")

    if not email or not wave_id:
        return jsonify({"success": False, "message": "Daten fehlen"}), 400

    try:
        db_path = mail_reader.get_db_path(int(campaign_id) if campaign_id else None)
    except (FileNotFoundError, ValueError):
        return jsonify({"success": False, "message": "Kampagne nicht gefunden"}), 404

    column = f"mail_{int(wave_id)}"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if column not in columns:
            return jsonify({"success": False, "message": "Unbekannte Mail-ID"}), 404
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "message": "Empfänger unbekannt"}), 404
        cursor.execute(
            f"UPDATE users SET {column} = ? WHERE id = ?",
            (cfg.STATUS_CLICKED, user[0]),
        )

    return jsonify({"success": True})


# --- Campaign helpers ------------------------------------------------------
def _list_campaign_ids():
    folder = Path(cfg.DATABASES_DIR)
    if not folder.exists():
        return []
    ids = []
    for p in folder.glob("campaign*.db"):
        digits = "".join(ch for ch in p.stem if ch.isdigit())
        if digits:
            ids.append(int(digits))
    return sorted(ids)


def _campaign_stats(campaign_id):
    db_path = os.path.join(cfg.DATABASES_DIR, f"campaign{campaign_id}.db")
    if not os.path.exists(db_path):
        return None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        mail_columns = [r[1] for r in cursor.fetchall() if r[1].startswith("mail_")]
        users_rows = cursor.execute("SELECT * FROM users").fetchall()

    totals = {cfg.STATUS_REPORTED: 0, cfg.STATUS_CLICKED: 0, cfg.STATUS_NO_RESPONSE: 0}
    per_mail = {c: dict(totals) for c in mail_columns}
    users = []
    for row in users_rows:
        mails = {}
        counts = {cfg.STATUS_REPORTED: 0, cfg.STATUS_CLICKED: 0, cfg.STATUS_NO_RESPONSE: 0}
        for c in mail_columns:
            value = row[c] or cfg.STATUS_NO_RESPONSE
            mails[c] = value
            counts[value] = counts.get(value, 0) + 1
            totals[value] = totals.get(value, 0) + 1
            per_mail[c][value] = per_mail[c].get(value, 0) + 1
        users.append({
            "id": row["id"],
            "name": row["name"],
            "lastname": row["lastname"],
            "email": row["email"],
            "reported": counts[cfg.STATUS_REPORTED],
            "clicked": counts[cfg.STATUS_CLICKED],
            "no_response": counts[cfg.STATUS_NO_RESPONSE],
            "mails": mails,
        })

    per_mail_list = [
        {"wave": int(c.split("_")[1]), **per_mail[c]}
        for c in sorted(mail_columns, key=lambda x: int(x.split("_")[1]))
    ]
    return {"totals": totals, "users": users, "per_mail": per_mail_list,
            "total_emails": len(mail_columns)}


# --- Campaign API ----------------------------------------------------------
@app.route("/api/campaigns", methods=["GET"])
@login_required
def list_campaigns():
    campaigns = [campaign_runner.get_status(cid) for cid in _list_campaign_ids()]
    return jsonify({"campaigns": [c for c in campaigns if c]})


@app.route("/api/campaigns", methods=["POST"])
@login_required
def create_campaign():
    data = request.get_json(silent=True) or {}
    config_file = data.get("config_file") or cfg.get_active_config_name()
    try:
        config = cfg.load_config(config_file)
    except (OSError, FileNotFoundError):
        return jsonify({"error": f"Config '{config_file}' nicht gefunden"}), 404
    db_path = data_creator.create_campaign_db(config, config_file)
    digits = "".join(ch for ch in Path(db_path).stem if ch.isdigit())
    return jsonify({"success": True, "campaign_id": int(digits)})


@app.route("/api/campaigns/<int:campaign_id>/start", methods=["POST"])
@login_required
def start_campaign(campaign_id):
    if campaign_runner.start_campaign(campaign_id):
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Läuft bereits oder unbekannt"}), 400


@app.route("/api/campaigns/<int:campaign_id>/stop", methods=["POST"])
@login_required
def stop_campaign(campaign_id):
    campaign_runner.stop_campaign(campaign_id)
    return jsonify({"success": True})


@app.route("/api/campaigns/<int:campaign_id>/status", methods=["GET"])
@login_required
def campaign_status(campaign_id):
    status = campaign_runner.get_status(campaign_id)
    if not status:
        return jsonify({"error": "Kampagne nicht gefunden"}), 404
    return jsonify(status)


@app.route("/api/campaigns/<int:campaign_id>/stats", methods=["GET"])
@login_required
def campaign_stats(campaign_id):
    stats = _campaign_stats(campaign_id)
    if stats is None:
        return jsonify({"error": "Kampagne nicht gefunden"}), 404
    return jsonify(stats)


@app.route("/api/campaigns/<int:campaign_id>/check-responses", methods=["POST"])
@login_required
def check_responses(campaign_id):
    try:
        updated = mail_reader.check_responses(campaign_id)
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "updated": updated})


# --- Users / CSV API -------------------------------------------------------
@app.route("/api/users", methods=["GET"])
@login_required
def list_users():
    if not os.path.exists(cfg.CSV_PATH):
        return jsonify({"users": []})
    with open(cfg.CSV_PATH, newline="", encoding="utf-8") as f:
        users = list(csv.DictReader(f))
    return jsonify({"users": users})


@app.route("/api/users/upload", methods=["POST"])
@login_required
def upload_users():
    file = request.files.get("csv_file")
    if not file or not file.filename.endswith(".csv"):
        return jsonify({"error": "Keine gültige CSV-Datei"}), 400
    os.makedirs(cfg.DATENBANKEN_DIR, exist_ok=True)
    file.save(cfg.CSV_PATH)
    with open(cfg.CSV_PATH, newline="", encoding="utf-8") as f:
        count = sum(1 for _ in csv.DictReader(f))
    return jsonify({"success": True, "count": count})


# --- Config (YAML) API -----------------------------------------------------
@app.route("/api/config/list", methods=["GET"])
@login_required
def list_config():
    return jsonify({"files": cfg.list_config_files(), "active": cfg.get_active_config_name()})


@app.route("/api/config/upload", methods=["POST"])
@login_required
def upload_config():
    file = request.files.get("yaml_file")
    if not file or not file.filename.endswith((".yml", ".yaml")):
        return jsonify({"error": "Keine gültige YAML-Datei"}), 400
    os.makedirs(cfg.DATENBANKEN_DIR, exist_ok=True)
    path = os.path.join(cfg.DATENBANKEN_DIR, file.filename)
    file.save(path)
    try:
        cfg.load_config(file.filename)  # validate
    except Exception:
        os.remove(path)
        return jsonify({"error": "Ungültiges YAML"}), 400
    cfg.set_active_config(file.filename)  # uploaded config becomes the active one
    return jsonify({"success": True, "filename": file.filename})


@app.route("/api/config/active", methods=["POST"])
@login_required
def set_active():
    filename = (request.get_json(silent=True) or {}).get("filename")
    if not filename:
        return jsonify({"error": "filename fehlt"}), 400
    cfg.set_active_config(filename)
    return jsonify({"success": True})


# --- Settings API ----------------------------------------------------------
@app.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    settings = cfg.get_settings()
    settings.pop("admin_password", None)   # never expose the password
    settings.pop("sender_password", None)  # never expose the mail password
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
@login_required
def update_settings():
    data = request.get_json(silent=True) or {}
    # Empty password fields must not overwrite stored secrets.
    for secret in ("admin_password", "sender_password"):
        if secret in data and data[secret] == "":
            data.pop(secret)
    cfg.save_settings(data)
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True)
