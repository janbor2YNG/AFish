import sqlite3
from pathlib import Path
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
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
conn.close()