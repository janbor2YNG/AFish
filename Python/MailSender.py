import csv
import os
import random
import smtplib
import yaml
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

with open("cpgn1.yaml", "r", encoding="utf-8") as file:
    config_cpgn = yaml.safe_load(file)
# Absender-Infos
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "teacherfisher.innen@gmail.com"
SENDER_PASSWORD = "czqc rfzf qijm vvnf"

# Betreff
subject = "PLATZHALTER"
variable_mail_body_randomnes = config_cpgn["mail_body_randomnesses"]


chosen_mail_body = "placeholder"
def declareMailBody(dateiname):
    # Dateipfad zusammensetzen
    mail_body_pfad = os.path.join(r"..\Server\Mails", dateiname)
    list_mail_bodys = [f for f in os.listdir(r"..\Server\Mails") if os.path.isfile(os.path.join(r"..\Server\Mails", f))]
    with open(fr"..\Server\Mails\{dateiname}", "r", encoding="utf-8") as file:
        mail_body = file.read()
    return mail_body

if input_body_randomnes:
    # Alle Dateien im Ordner auflisten (nur Dateien, keine Unterordner)
    list_mail_bodys = [f for f in os.listdir(r"..\Server\Mails") if os.path.isfile(os.path.join(r"..\Server\Mails", f))]
    # Zufällige Datei auswählen
    chosen_mail_body = random.choice(list_mail_bodys)
    print(f"Chosen mail: {chosen_mail_body}")
    mail_body = declareMailBody(chosen_mail_body)
else:
    mail_body_type = (input("Which body type(s) do you want? (Google [g], Office [o]) Multiple [a,b,c,etc.]"))
    chosen_mail_body = mail_body_type[0]
    match mail_body_type:
        case "g": chosen_mail_body = "Google_Sicherheitswarnung.html"
        case "o": chosen_mail_body = "TEST_mail.html"
    print(f"Chosen mail: {chosen_mail_body}")
    mail_body = declareMailBody(chosen_mail_body)

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
