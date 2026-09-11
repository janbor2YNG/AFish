"""Phishing mail sending engine.

Sending is exposed as plain functions that the campaign runner / Flask app can
call. Credentials and the dry-run flag come from ``config_manager`` (settings.json).

Model:
* ``total_waves`` in the YAML = number of mail waves.
* Each wave sends one templated mail to every recipient, carrying the wave id.
* Every send is logged as one row in the campaign's ``events`` table, which is
  what tracking, statistics and the Excel export are built from.
"""

import os
import re
import sys
import random
import secrets
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402


def build_distribution_plan(start_date, end_date, wave_count):
    """Spread ``wave_count`` waves across the date range.

    Returns a dict ``{"DD.MM.YYYY": number_of_waves}``.
    """
    start = datetime.strptime(start_date, "%d.%m.%Y")
    end = datetime.strptime(end_date, "%d.%m.%Y")

    days = (end - start).days + 1
    if days <= 0:
        return {start.strftime("%d.%m.%Y"): wave_count}

    per_day = [wave_count // days] * days
    remainder = wave_count % days
    for i in random.sample(range(days), remainder):
        per_day[i] += 1

    plan = {}
    for offset, waves in enumerate(per_day):
        day = (start + timedelta(days=offset)).strftime("%d.%m.%Y")
        plan[day] = waves
    return plan


def waves_due_by(plan, reference_date=None):
    """Cumulative number of waves that should have been sent by ``reference_date``."""
    reference_date = reference_date or datetime.now()
    due = 0
    for day, count in plan.items():
        if datetime.strptime(day, "%d.%m.%Y").date() <= reference_date.date():
            due += count
    return due


def load_template(name):
    """Read a mail template HTML file from Server/Mails."""
    if not name.endswith(".html"):
        name = name + ".html"
    with open(os.path.join(cfg.MAILS_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DEFAULT_SUBJECT = "Wichtige Information"


def extract_subject(template_html):
    """The mail subject is not configurable in Settings - it comes from the
    template's own <title> tag, so the subject always matches whatever
    template was actually used (uploading a new template with a new subject
    just works, without touching Settings at all). Falls back to a generic
    default if a template has no <title>."""
    match = TITLE_RE.search(template_html)
    if not match:
        return DEFAULT_SUBJECT
    subject = re.sub(r"\s+", " ", match.group(1)).strip()
    return subject or DEFAULT_SUBJECT


def get_recipients(db_path):
    """Return the campaign's recipients as a list of dicts."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users")
        rows = cursor.fetchall()
    return [{"id": r[0], "name": r[1], "email": r[2]} for r in rows]


def _campaign_id_from_path(db_path):
    match = re.search(r"\d+", os.path.basename(str(db_path)))
    return int(match.group()) if match else 0


def _build_link(base_url, campaign_id, token):
    """Build the tracking link. Carries only an opaque per-message token - no
    recipient e-mail or wave number in the URL, so nothing personal ends up in
    browser history, server logs or intermediate proxies."""
    base_url = (base_url or "").rstrip("/")
    return f"{base_url}/click/{campaign_id}/{token}"


def choose_template(config):
    """Pick a random template name from the campaign's template list."""
    templates = config.get("templates") or ["office-login"]
    return random.choice(templates)


def send_wave(wave_id, db_path, config, settings=None, logger=print):
    """Send a single wave to all recipients of the campaign.

    In dry-run mode nothing is sent - the action is only logged. Either way,
    one ``events`` row per recipient is written so tracking/statistics/export
    all work identically in dry-run and real mode. Returns the number of mails
    (notionally) sent.
    """
    settings = settings or cfg.get_settings()
    recipients = get_recipients(db_path)
    campaign_id = _campaign_id_from_path(db_path)
    template_name = choose_template(config)
    template = load_template(template_name)
    category, sender = cfg.get_sender_for_template(template_name)
    subject_template = extract_subject(template)
    base_url = settings.get("tracking_base_url", "http://127.0.0.1:5000")
    dry_run = settings.get("dry_run", True)
    now = datetime.now().isoformat(timespec="seconds")

    if not dry_run:
        server = smtplib.SMTP(settings["smtp_server"], int(settings["smtp_port"]))
        server.starttls()
        server.login(settings["sender_email"], settings["sender_password"])

    sent = 0
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for r in recipients:
            token = secrets.token_urlsafe(16)
            link = _build_link(base_url, campaign_id, token)
            body = template.format(id=wave_id, name=r["name"], user_mail=r["email"], link=link)
            try:
                subject = subject_template.format(id=wave_id, name=r["name"], user_mail=r["email"])
            except (KeyError, IndexError):
                # A custom template's <title> may contain a stray "{"/"}" that
                # isn't meant as a placeholder - fall back to it verbatim
                # rather than failing the whole send.
                subject = subject_template

            if dry_run:
                logger(f"[DRY-RUN] Wave {wave_id}: would send '{template_name}' to {r['email']}")
            else:
                message = MIMEMultipart()
                message["From"] = f"{sender['name']} <{sender['email']}>"
                message["To"] = r["email"]
                message["Subject"] = subject
                message.attach(MIMEText(body, "html"))
                server.sendmail(sender["email"], r["email"], message.as_string())
                logger(f"Sent wave {wave_id} ('{template_name}') to {r['email']}")

            cursor.execute(
                """INSERT INTO events (user_id, wave, category, template, sender_name,
                                        sender_email, status, token, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r["id"], wave_id, category, template_name, sender["name"], sender["email"],
                 cfg.STATUS_SENT, token, now),
            )
            sent += 1

    if not dry_run:
        server.quit()
    return sent
