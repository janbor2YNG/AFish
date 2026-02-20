import sqlite3
import yaml
import csv
from pathlib import Path
# YAML laden
with open(r"..\Server\Datenbanken\cpgn1.yaml", "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

total_mails = config["send"]["total_emails"]


def create_connection():
    #Ordner festlegen
    folder = Path("databases")
    #erstellen, falls er noch nicht existiert
    folder.mkdir(exist_ok=True)
    #Zähler starten
    counter = 1
    #Solange die Datei existiert, erhöhe den Zähler
    def find_path_db(counter):
        while (folder / f"campaign{counter}.db").exists():
            counter += 1
        #Freien Dateinamen erstellen
        db_path = folder / f"campaign{counter}.db"
        return db_path
    db_path = find_path_db(counter)
    #Datenbank erstellen
    conn = sqlite3.connect(db_path)
    print(f"Neue Datenbank erstellt: {db_path}")
    conn.close()
    return db_path
db_path = create_connection()

# Spalten dynamisch generieren
mail_spalten = ""
for i in range(1, total_mails + 1):
    mail_spalten += (
        f"    mail_{i} TEXT DEFAULT 'nicht beantwortet' "
        f"CHECK(mail_{i} IN ('bestanden', 'durchgefallen', 'nicht beantwortet')),\n"
    )
mail_spalten = mail_spalten.rstrip(",\n")

sql_quest = f"""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        lastname TEXT,
        email TEXT,
    {mail_spalten}
    )
    """
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    cursor.execute(sql_quest)
conn.close()
# Filterkriterien aus YAML
include_roles = config.get("target", {}).get("include_role") or []
exclude_roles = config.get("target", {}).get("exclude_role") or []
required_fach = config.get("target", {}).get("fach") or []
min_alter     = config.get("target", {}).get("min_alter") or 0

def user_erlaubt(row):
    rolle     = row.get("role", "").strip()
    alter_str = row.get("age", "0").strip()
    faecher   = {(row.get("sub1") or "").strip(), (row.get("sub2") or "").strip()}

    try:
        alter = int(alter_str)
    except ValueError:
        return False

    if alter < min_alter:
        return False
    if rolle in exclude_roles:
        return False
    if include_roles and rolle not in include_roles:
        return False
    if required_fach and not faecher.intersection(required_fach):
        return False

    return True

with open(r"..\Server\Datenbanken\current_user_list.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    empfaenger = [row for row in reader if user_erlaubt(row)]

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    for row in empfaenger:
        name     = (row.get("name") or "").strip()
        lastname = (row.get("lastname") or "").strip()
        email    = (row.get("email") or "").strip()

        if not email:
            print(f"Übersprungen (keine Email): {name} {lastname}")
            continue

        try:
            cursor.execute("""
                INSERT INTO users (name, lastname, email)
                VALUES (?, ?, ?)
            """, (name, lastname, email))
        except Exception as e:
            print(f"Fehler bei {name} {lastname}: {e}")

    conn.commit()
    print(f"{len(empfaenger)} User in Datenbank eingetragen.")