import flask
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
from flask import Flask, request, jsonify
from MailSender import mailsender

app = Flask(__name__)
saved_emails = []
@app.route('/')
def Start():
  with open("fakeWebsite.html") as file:
    return file.read()



@app.route('/apply', methods=['POST'])
def apply():
    data = request.json
    email = data.get('email')
    user_id = data.get('id')

    if not email:
        return jsonify({"success": False, "message": "Email fehlt!"}), 400

    # Speichern oder Weiterverarbeiten
    saved_emails.append({"email": email, "id": user_id})
    print(f"Gespeichert: {email} mit ID {user_id}")

    return jsonify({"success": True, "message": f"{email} wurde eingetragen."})


if __name__ == "__main__":
    # Server starten auf localhost:5000
    app.run(debug=True)