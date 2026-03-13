from flask import Flask, request, jsonify, session
import sqlite3
from pathlib import Path
import re
import yaml

import os

from config_manager import get_config, set_active_config
app = Flask(__name__)
saved_emails = []
@app.route('/')
def Start():
  with open("test.html") as file:
    return file.read()
@app.route("/failed_set_status.html")
def fakewebfro():
  with open("/failed_set_status.html") as file:
    return file.read()
@app.route("/fakeWebsiteBackend.js")
def fakwebbac():
  with open("fakeWebsiteBackend.js") as file:
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

    def get_latest_db() -> Path:
        base_dir = Path(__file__).resolve()

        folder = base_dir.parents[2] / "Python" / "databases"

        dbs = sorted(
            folder.glob("campaign*.db"),
            key=lambda p: int(re.search(r'\d+', p.stem).group())
        )

        if not dbs:
            raise FileNotFoundError("Keine campaign*.db Datenbank gefunden!")

        return dbs[-1]

    db_path = get_latest_db()
    print(f"Verbinde mit Datenbank: {db_path}")

    print(f"Gespeichert: {email} mit ID {user_id}")
    mail_nr = int(user_id)
    print(f"Von: {email} → ID gefunden: mh{mail_nr}")
    spalte = f"mail_{mail_nr}"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        spalten = [row[1] for row in cursor.fetchall()]
        if spalte not in spalten:
            print(f"Spalte '{spalte}' existiert nicht – übersprungen.")
        else:
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
            if not user:
                print(f"User '{email}' nicht gefunden – übersprungen.")
            else:
                try:
                    cursor.execute(f"UPDATE users SET {spalte} = ? WHERE id = ?", ("bestanden", user[0]))
                    print(f"✓ {email} → {spalte} = 'durchgefallen'")
                except sqlite3.IntegrityError:
                    print(f"✗ Ungültiger Status")

    return jsonify({"success": True, "message": f"{email} wurde eingetragen."})

app.secret_key = 'your-secret-key'
UPLOAD_FOLDER = '../Datenbanken'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route('/upload-yaml', methods=['POST'])
def upload_yaml():
    file = request.files.get('yaml_file')
    if not file or not file.filename.endswith(('.yml', '.yaml')):
        return jsonify({'error': 'Invalid file'}), 400

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # Validate it's valid YAML
    with open(filepath) as f:
        yaml.safe_load(f)

    return jsonify({'message': 'Uploaded', 'filename': file.filename})

@app.route('/set-active-config', methods=['POST'])
def set_active():
    filename = request.json.get('filename')
    set_active_config(filename)  # schreibt in active_config.txt
    return jsonify({'message': f'{filename} ist jetzt aktiv'})


@app.route('/list-configs', methods=['GET'])
def list_configs():
    files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(('.yml', '.yaml'))]
    active = session.get('active_config')
    return jsonify({'files': files, 'active': active})
def get_config():
    active = session.get('active_config', 'default.yaml')
    with open(os.path.join(UPLOAD_FOLDER, active)) as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    # Server starten auf localhost:5000
    app.run(debug=True)