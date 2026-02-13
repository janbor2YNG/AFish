
import csv
import os
import random
import smtplib
import yaml
import schedule
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
def mailsender():
    with open("../Server/Datenbanken/cpgn1.yaml", "r", encoding="utf-8") as file:
        config_cpgn = yaml.safe_load(file)
    id = 0
    # Absender-Infos
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = "teacherfisher.innen@gmail.com"
    SENDER_PASSWORD = "czqc rfzf qijm vvnf"

    START = config_cpgn["send"]["timeframe"]["start"]       # "01.01.2026"
    END = config_cpgn["send"]["timeframe"]["end"]           # "01.02.2026"
    MAIL_COUNT = config_cpgn["send"]["total_emails"]  # z.B. 100
    start_time = "15:26"
    start_time_zum_rechnen = 14
    # Betreff
    subject = "PLATZHALTER"
    mail_body_randomnes = config_cpgn["mail_body_randomnes"]

    def verteile_mails(startdatum, enddatum, mail_count):
        start = datetime.strptime(startdatum, "%d.%m.%Y")
        end = datetime.strptime(enddatum, "%d.%m.%Y")

        tage = (end - start).days + 1

        mails_pro_tag = [mail_count // tage] * tage
        rest = mail_count % tage

        for i in random.sample(range(tage), rest):
            mails_pro_tag[i] += 1

        plan = {}
        for offset, mails in enumerate(mails_pro_tag):
            tag = (start + timedelta(days=offset)).strftime("%d.%m.%Y")
            plan[tag] = mails

        return plan

    VERTEILPLAN = verteile_mails(START, END, MAIL_COUNT)
    def daily_job():
        heute = datetime.now().strftime("%d.%m.%Y")
        global VERTEILPLAN

        if heute not in VERTEILPLAN:
            print("Heute müssen keine Mails versendet werden.")
            return

        anzahl = VERTEILPLAN[heute]
        if anzahl <= 1:
            waiting_time = 0
        else:
            gesamtzeit = (24-start_time_zum_rechnen) // (anzahl-1)*3600
            geteilte_zeit = gesamtzeit // (anzahl - 1)
            if geteilte_zeit <= 0:
                waiting_time = 0
            else:
                waiting_time = random.randrange(0, geteilte_zeit)
        print(f"waiting_time{waiting_time}.sekunden")
        print(f"Heute ({heute}) werden {anzahl} Mails verschickt.")
        send_mail(anzahl, waiting_time)


    chosen_mail_body = "placeholder"
    def declareMailBody(dateiname):
        # Dateipfad zusammensetzen
        mail_body_pfad = os.path.join(r"../Server/Mails", dateiname)
        list_mail_bodys = [f for f in os.listdir(r"../Server/Mails") if os.path.isfile(os.path.join(r"../Server/Mails", f))]
        with open(fr"../Server/Mails/{dateiname}", "r", encoding="utf-8") as file:
            mail_body = file.read()
        return mail_body
    def send_mail(anzahl, waiting_time):


        for i in range(anzahl):
            global id
            id += 1
            with open(r"../Server/Datenbanken/current_user_list.csv", newline="", encoding="utf-8") as f:
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
                        body = mail_body.format(id=id, name=name, lastname=lastname, user_mail=user_mail)
                        mime_message.attach(MIMEText(body, "html"))

                        # Mail senden
                        server.sendmail(SENDER_EMAIL, user_mail, mime_message.as_string())
                        print(f"Sent to: {user_mail}")
            time.sleep(waiting_time)
        return id



    list_mail_bodys = config_cpgn["body_template"]

    schedule.every().day.at(start_time).do(daily_job)

    # Zufällige Datei auswählen
    chosen_mail_body = str(random.choice(list_mail_bodys) + ".html")
    print(f"Chosen mail: {chosen_mail_body}")
    mail_body = declareMailBody(chosen_mail_body)

    while True:
        schedule.run_pending()