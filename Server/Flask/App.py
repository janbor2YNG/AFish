"""AFish - central Flask application.

This is the single entry point that hosts the whole phishing-simulation tool:
admin authentication, the dashboard, all JSON APIs (campaigns, stats, users,
templates, config, settings), the Excel export and the public phishing-tracking
endpoints.
"""

import os
import io
import sys
import csv
import time
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask, request, jsonify, session, redirect,
    send_from_directory, send_file, url_for, Response,
)

# When stdout is redirected to a log file (nohup, systemd, ...) rather than a
# terminal, Python fully buffers it by default - every print() in this app
# and in the engine modules (mail_sender/mail_reader/campaign_runner all log
# via plain print()) can then sit unflushed for a long time, making the logs
# useless for diagnosing "nothing happened" reports. Force line buffering so
# log lines show up as they happen.
sys.stdout.reconfigure(line_buffering=True)

# Local (Server/Flask) + engine (Python/) imports.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)  # so config_manager resolves regardless of cwd
sys.path.insert(0, os.path.join(BASE_DIR, "..", "..", "Python"))

import config_manager as cfg          # noqa: E402
import data_creator                   # noqa: E402
import mail_reader                    # noqa: E402
import campaign_runner                # noqa: E402
import stats as stats_mod             # noqa: E402
import excel_export                   # noqa: E402

HTML_DIR = os.path.join(cfg.REPO_ROOT, "UI", "HTML")

app = Flask(
    __name__,
    static_folder=os.path.join(cfg.REPO_ROOT, "UI"),
    static_url_path="/static",
)
# Session secret: must come from the environment on a real deployment (never
# commit a secret to source). Falls back to a random per-process key so the
# app still starts for local/dry-run use - existing sessions just won't
# survive a restart in that case.
app.secret_key = os.environ.get("AFISH_SECRET_KEY") or secrets.token_hex(32)
if not os.environ.get("AFISH_SECRET_KEY"):
    print("[AFish] AFISH_SECRET_KEY not set - using a random session secret "
          "for this process only. Set it in the environment for production use.")


# --- Authentication --------------------------------------------------------
# Very small in-memory brute-force guard: block an IP for a while after too
# many failed logins in a row. Simple on purpose - no extra dependency, and
# a restart of the internal server resets it, which is acceptable here.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60
_login_attempts = {}  # ip -> (fail_count, locked_until_timestamp)


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
    ip = request.remote_addr or "unknown"
    fail_count, locked_until = _login_attempts.get(ip, (0, 0))
    if time.time() < locked_until:
        wait = int(locked_until - time.time())
        return jsonify({"success": False,
                         "message": f"Zu viele Fehlversuche, bitte {wait}s warten."}), 429

    data = request.get_json(silent=True) or request.form
    password = data.get("password", "")
    if password == cfg.get_setting("admin_password"):
        session["logged_in"] = True
        _login_attempts.pop(ip, None)
        return jsonify({"success": True})

    fail_count += 1
    locked_until = time.time() + LOGIN_LOCKOUT_SECONDS if fail_count >= LOGIN_MAX_ATTEMPTS else 0
    _login_attempts[ip] = (fail_count, locked_until)
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
@app.route("/click/<int:campaign_id>/<token>")
def click(campaign_id, token):
    """Public landing hit when a teacher clicks the simulated phishing link.

    The URL carries only an opaque per-message token - no recipient e-mail
    address, name or wave number - so nothing personal leaks into browser
    history, server access logs or intermediate proxies. Marks the matching
    event as ``clicked`` (unless it was already correctly ``reported``, which
    always wins) and forwards straight to the awareness page. No real
    credentials are ever requested. No login required by design.
    """
    try:
        db_path = mail_reader.get_db_path(campaign_id)
    except FileNotFoundError:
        print(f"[click] campaign {campaign_id} has no database (deleted/reset?) - "
              f"token {token} ignored, link is stale")
        return redirect(url_for("awareness"))

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """UPDATE events SET status = ?, clicked_at = ?
               WHERE token = ? AND status != ?""",
            (cfg.STATUS_CLICKED, datetime.now().isoformat(timespec="seconds"),
             token, cfg.STATUS_REPORTED),
        )
        if cursor.rowcount == 0:
            print(f"[click] campaign {campaign_id}: token not found (or already reported) "
                  f"- link is stale or was already correctly reported")
    return redirect(url_for("awareness"))


@app.route("/awareness")
def awareness():
    """Educational page shown after a simulated phishing link was clicked."""
    return (
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
        "<title>Phishing-Simulation</title></head>"
        "<body style='font-family:sans-serif;max-width:640px;margin:60px auto;line-height:1.6'>"
        "<h1>Dies war eine Phishing-Simulation</h1>"
        "<p>Diese E-Mail war Teil einer autorisierten Sensibilisierungs-Massnahme Ihrer "
        "Schule. Echte Angreifer hätten an dieser Stelle versucht, Ihre Zugangsdaten zu "
        "stehlen - es wurden keinerlei Daten von Ihnen abgefragt oder gespeichert.</p>"
        "<h2 style='margin-top:24px;font-size:1.1rem;'>Woran Sie eine solche Mail erkennen</h2>"
        "<ul><li>Dringlichkeit und Handlungsdruck (\"sofort handeln\", \"Konto wird gesperrt\")</li>"
        "<li>Abweichende oder unpersönliche Absenderadresse</li>"
        "<li>Link-Ziel weicht von der erwarteten Domain ab (Mauszeiger über den Link halten)</li>"
        "<li>Aufforderung, sich \"aus Sicherheitsgründen\" erneut anzumelden</li></ul>"
        "<p style='margin-top:24px;'>Bitte melden Sie verdächtige E-Mails künftig an Ihre "
        "IT-Sicherheitsbeauftragten, statt auf enthaltene Links zu klicken.</p></body></html>"
    )


# --- Campaign API ----------------------------------------------------------
@app.route("/api/campaigns", methods=["GET"])
@login_required
def list_campaigns():
    campaigns = [campaign_runner.get_status(cid) for cid in stats_mod.list_campaign_ids()]
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
    if not os.path.exists(cfg.CSV_PATH):
        return jsonify({"error": "Keine Empfängerliste (CSV) hochgeladen"}), 400
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
    result = stats_mod.campaign_stats(campaign_id)
    if result is None:
        return jsonify({"error": "Kampagne nicht gefunden"}), 404
    return jsonify(result)


@app.route("/api/campaigns/<int:campaign_id>/export.xlsx", methods=["GET"])
@login_required
def campaign_export(campaign_id):
    try:
        buf = excel_export.build_campaign_workbook(campaign_id)
    except FileNotFoundError:
        return jsonify({"error": "Kampagne nicht gefunden"}), 404
    name = f"kampagne-{campaign_id}-ergebnisse.xlsx"
    return send_file(
        buf, as_attachment=True, download_name=name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/campaigns/<int:campaign_id>/export-raw.csv", methods=["GET"])
@login_required
def campaign_export_raw(campaign_id):
    """Plain per-teacher raw-numbers CSV - exactly the counts shown in the
    Statistiken table (received/clicked/reported), with no percentages or
    other computed values, so the evaluation can be independently
    recalculated from first principles rather than trusting the Excel export."""
    data = stats_mod.campaign_stats(campaign_id)
    if data is None:
        return jsonify({"error": "Kampagne nicht gefunden"}), 404

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "E-Mail", "Gruppe", "Mails erhalten", "Geklickt",
                      "Korrekt gemeldet", "Mehrfach nicht erkannt"])
    for u in data["users"]:
        writer.writerow([
            u["name"], u["email"], u["gruppe"] or "", u["sent"], u["clicked"],
            u["reported"], "Ja" if u["repeat_fail"] else "Nein",
        ])

    name = f"kampagne-{campaign_id}-rohdaten.csv"
    # utf-8-sig so Excel opens umlauts correctly instead of guessing the wrong encoding.
    return Response(
        buf.getvalue().encode("utf-8-sig"), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.route("/api/campaigns/compare", methods=["GET"])
@login_required
def campaigns_compare():
    return jsonify({"campaigns": stats_mod.compare_campaigns()})


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
        reader = csv.DictReader(f)
        if not reader.fieldnames or "email" not in reader.fieldnames:
            os.remove(cfg.CSV_PATH)
            return jsonify({"error": "CSV benötigt mindestens eine Spalte 'email'"}), 400
        count = sum(1 for _ in reader)
    return jsonify({"success": True, "count": count})


# --- Templates API -----------------------------------------------------------
@app.route("/api/templates", methods=["GET"])
@login_required
def list_templates():
    if not os.path.isdir(cfg.MAILS_DIR):
        return jsonify({"templates": []})
    profiles = cfg.get_sender_profiles()
    templates = []
    for fname in sorted(os.listdir(cfg.MAILS_DIR)):
        if not fname.endswith(".html"):
            continue
        name = fname[:-5]
        category = name.split("-")[0]
        templates.append({
            "name": name,
            "category": category,
            "sender": profiles.get(category),
        })
    return jsonify({"templates": templates})


@app.route("/api/templates/upload", methods=["POST"])
@login_required
def upload_template():
    file = request.files.get("html_file")
    if not file or not file.filename.endswith(".html"):
        return jsonify({"error": "Keine gültige HTML-Datei"}), 400
    filename = os.path.basename(file.filename)
    os.makedirs(cfg.MAILS_DIR, exist_ok=True)
    file.save(os.path.join(cfg.MAILS_DIR, filename))
    return jsonify({"success": True, "filename": filename})


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
    # Bound to localhost and debug-off by default. For recipients on other
    # machines to reach /click links (and for the report-inbox check to be
    # testable end to end), the server needs to listen on the school
    # network's actual address - set AFISH_HOST=0.0.0.0 (or the server's LAN
    # IP) and make sure "Tracking-Basis-URL" in den Einstellungen points at
    # that same address, not 127.0.0.1. Leave AFISH_DEBUG unset (or "false")
    # outside of local development: Flask's debug mode (a) can expose an
    # interactive code-execution debugger to anyone who can reach the
    # server, and (b) auto-restarts the whole process on file changes, which
    # silently kills the background campaign-sending/report-checking thread.
    host = os.environ.get("AFISH_HOST", "127.0.0.1")
    port = int(os.environ.get("AFISH_PORT", "5000"))
    debug = os.environ.get("AFISH_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
