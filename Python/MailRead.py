import imaplib
import email
import re
import yaml
import sqlite3
import csv
from pathlib import Path
from email.utils import parseaddr
from datetime import datetime, timedelta

def get_latest_db() -> Path:
    folder = Path("databases")
    dbs = sorted(
        folder.glob("campaign*.db"),
        key=lambda p: int(re.search(r'\d+', p.stem).group())
    )
    if not dbs:
        raise FileNotFoundError("Keine campaign*.db Datenbank gefunden!")
    return dbs[-1]

with open("../Server/Datenbanken/cpgn1.yaml", "r", encoding="utf-8") as file:
    config_cpgn = yaml.safe_load(file)
# 1. Verbindung zum Server herstellen
IMAP_SERVER = 'imap.gmail.com'  # Beispiel: Gmail
EMAIL_ACCOUNT = 'teacherfisher.innen@gmail.com'
PASSWORD = 'czqc rfzf qijm vvnf'  # bei Gmail z.B. App-Passwort nötig

# Deutsche Datumsangaben eingeben
START_DATE_DE = config_cpgn["send"]["timeframe"]["start"]
END_DATE_DE   = config_cpgn["send"]["timeframe"]["end"]

def to_imap_date(date_str):
    dt = datetime.strptime(date_str, "%d.%m.%Y")
    return dt.strftime("%d-%b-%Y")

START_DATE = to_imap_date(START_DATE_DE)
END_DATE = to_imap_date(END_DATE_DE)

db_path = get_latest_db()
print(f"Verbinde mit Datenbank: {db_path}")

# Verbindung aufbauen
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL_ACCOUNT, PASSWORD)
mail.select('inbox')

# Mails zwischen zwei Daten suchen
search_criterion = f'(SINCE "{START_DATE}" BEFORE "{END_DATE}")'
status, messages = mail.search(None, search_criterion)
email_ids = messages[0].split()

for e_id in email_ids:
    status, msg_data = mail.fetch(e_id, '(RFC822)')
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    # Nur die Mailadresse extrahieren
    sender_email = parseaddr(msg['From'])[1]

    # Body extrahieren
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or 'utf-8'
                body += part.get_payload(decode=True).decode(charset, errors='replace')
    else:
        charset = msg.get_content_charset() or 'utf-8'
        body = msg.get_payload(decode=True).decode(charset, errors='replace')

    # Prüfen auf genau 'id' direkt gefolgt von Zahl (z.B. id123)
    match = re.search(r'\bmh(\d+)\b', body, re.IGNORECASE)
    # ALT:
    if match:
        print(f"Von: {sender_email} → Gefunden: id{match.group(1)}")

    # NEU:
    if match:
        mail_nr = int(match.group(1))
        print(f"Von: {sender_email} → ID gefunden: mh{mail_nr}")
        spalte = f"mail_{mail_nr}"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            spalten = [row[1] for row in cursor.fetchall()]
            if spalte not in spalten:
                print(f"Spalte '{spalte}' existiert nicht – übersprungen.")
            else:
                cursor.execute("SELECT id FROM users WHERE email = ?", (sender_email,))
                user = cursor.fetchone()
                if not user:
                    print(f"User '{sender_email}' nicht gefunden – übersprungen.")
                else:
                    try:
                        cursor.execute(f"UPDATE users SET {spalte} = ? WHERE id = ?", ("bestanden", user[0]))
                        print(f"✓ {sender_email} → {spalte} = 'bestanden'")
                    except sqlite3.IntegrityError:
                        print(f"✗ Ungültiger Status")

