"""Phishing mail sending engine.

REFACTORED from the former ``MailSender.py``: the ``while True`` scheduler loop
and all hard-coded credentials are gone. Sending is now exposed as plain
functions that the campaign runner / Flask app can call. Credentials and the
dry-run flag come from ``config_manager`` (settings.json).

Model (unchanged from the original intent):
* ``total_emails`` in the YAML = number of mail *waves*.
* Each wave sends one templated mail to every recipient, carrying the wave id.
* The recipient's ``mail_<wave>`` column tracks how they reacted to that wave.
"""

import os
import re
import sys
import random
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "Server", "Flask"))

import config_manager as cfg  # noqa: E402


def build_distribution_plan(start_date, end_date, mail_count):
    """Spread ``mail_count`` waves across the date range (former verteile_mails).

    Returns a dict ``{"DD.MM.YYYY": number_of_waves}``.
    """
    start = datetime.strptime(start_date, "%d.%m.%Y")
    end = datetime.strptime(end_date, "%d.%m.%Y")

    days = (end - start).days + 1
    if days <= 0:
        return {start.strftime("%d.%m.%Y"): mail_count}

    per_day = [mail_count // days] * days
    remainder = mail_count % days
    for i in random.sample(range(days), remainder):
        per_day[i] += 1

    plan = {}
    for offset, mails in enumerate(per_day):
        day = (start + timedelta(days=offset)).strftime("%d.%m.%Y")
        plan[day] = mails
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
    """Read a mail template HTML file from Server/Mails (former declareMailBody)."""
    if not name.endswith(".html"):
        name = name + ".html"
    with open(os.path.join(cfg.MAILS_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def get_recipients(db_path):
    """Return the campaign's recipients as a list of dicts."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, lastname, email FROM users")
        rows = cursor.fetchall()
    return [{"id": r[0], "name": r[1], "lastname": r[2], "email": r[3]} for r in rows]


def _campaign_id_from_path(db_path):
    match = re.search(r"\d+", os.path.basename(str(db_path)))
    return int(match.group()) if match else 0


def _build_link(base_url, campaign_id, wave_id, email):
    base_url = (base_url or "").rstrip("/")
    return f"{base_url}/track?c={campaign_id}&id={wave_id}&email={email}"


def choose_template(config):
    """Pick a template name based on the campaign config."""
    templates = config.get("body_template") or ["test"]
    if config.get("mail_body_randomnes"):
        return random.choice(templates)
    return templates[0]


def send_wave(wave_id, db_path, config, settings=None, logger=print):
    """Send a single wave to all recipients of the campaign.

    In dry-run mode nothing is sent – the action is only logged. Returns the
    number of mails (notionally) sent.
    """
    settings = settings or cfg.get_settings()
    recipients = get_recipients(db_path)
    campaign_id = _campaign_id_from_path(db_path)
    template_name = choose_template(config)
    template = load_template(template_name)
    subject = settings.get("mail_subject", "Information")
    base_url = settings.get("tracking_base_url", "http://127.0.0.1:5000")
    dry_run = settings.get("dry_run", True)

    if dry_run:
        logger(
            f"[DRY-RUN] Wave {wave_id}: would send template '{template_name}' "
            f"to {len(recipients)} recipient(s)."
        )
        return len(recipients)

    sent = 0
    with smtplib.SMTP(settings["smtp_server"], int(settings["smtp_port"])) as server:
        server.starttls()
        server.login(settings["sender_email"], settings["sender_password"])
        for r in recipients:
            link = _build_link(base_url, campaign_id, wave_id, r["email"])
            body = template.format(
                id=wave_id,
                name=r["name"],
                lastname=r["lastname"],
                user_mail=r["email"],
                link=link,
            )
            message = MIMEMultipart()
            message["From"] = settings["sender_email"]
            message["To"] = r["email"]
            message["Subject"] = subject
            message.attach(MIMEText(body, "html"))
            server.sendmail(settings["sender_email"], r["email"], message.as_string())
            logger(f"Sent wave {wave_id} to {r['email']}")
            sent += 1
    return sent
