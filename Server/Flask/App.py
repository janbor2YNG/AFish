from flask import Flask, request, jsonify
import sqlite3
from pathlib import Path
import re

app = Flask(__name__)
saved_emails = []
@app.route('/')
def Start():
  with open("failed_set_status.html") as file:
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
                    print(f"✓ {email} → {spalte} = 'bestanden'")
                except sqlite3.IntegrityError:
                    print(f"✗ Ungültiger Status")

    return jsonify({"success": True, "message": f"{email} wurde eingetragen."})


if __name__ == "__main__":
    # Server starten auf localhost:5000
    app.run(debug=True)