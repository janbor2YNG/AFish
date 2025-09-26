import csv
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Absender-Infos
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "teacherfisher.innen@gmail.com"
SENDER_PASSWORD = "czqc rfzf qijm vvnf"

# Betreff
subject = "PLATZHALTER"
# Alle Dateien im Ordner auflisten (nur Dateien, keine Unterordner)
chose_random_mail_body = [f for f in os.listdir(r"..\Server\Mails") if os.path.isfile(os.path.join(r"..\Server\Mails", f))]

# Zufällige Datei auswählen
random_mail_body = random.choice(chose_random_mail_body)
print(f"Chosen mail: {random_mail_body}")
with open (fr"..\Server\Mails\{random_mail_body}", "r", encoding="utf-8") as file:
    mail_body = file.read()


# CSV einlesen
with open(r"..\Server\Datenbanken\current_user_list.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    # SMTP-Verbindung einmal öffnen
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        for row in reader:
            user_mail = row["email"].strip()
            name = row["name"].strip()
            lastname = row["lastname"].strip()

            # Mail zusammenbauen
            mime_message = MIMEMultipart()
            mime_message["From"] = SENDER_EMAIL
            mime_message["To"] = user_mail
            mime_message["Subject"] = subject

            # Individueller Text
            body = mail_body.format(name=name, lastname=lastname, user_mail=user_mail)
            mime_message.attach(MIMEText(body, "html"))


            # Mail senden
            server.sendmail(SENDER_EMAIL, user_mail, mime_message.as_string())
            print(f"Sent to: {user_mail}")
