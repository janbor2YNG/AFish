# Abschlussbericht – Web-Integration der AFish Phishing-Simulation

Dieses Dokument fasst die durchgeführte Umsetzung zusammen: die gesamte
Anwendung läuft jetzt als **eine** über Flask gehostete Webanwendung, in der
alle Funktionen über die Oberfläche steuerbar sind. Es existieren keine toten
Buttons oder nicht erreichbaren Endpunkte mehr.

> **Ethischer Rahmen:** Werkzeug zur kontrollierten, einvernehmlichen
> Sensibilisierung von Lehrkräften (Hessisches Medienzentrum Seeheim). Kein
> Echtversand im Auslieferungszustand – siehe Dry-Run.

---

## 1. Überblick der Architektur

```
Browser (Dashboard / Login)
        │  fetch() JSON-API
        ▼
Server/Flask/App.py  ── Auth, Dashboard, REST-API, Phishing-Tracking
        │ importiert
        ├── config_manager.py   Pfade, aktive YAML, settings.json
        ├── Python/data_creator.py     create_campaign_db()
        ├── Python/mail_sender.py      Versand-Engine (Dry-Run-fähig)
        ├── Python/mail_reader.py      IMAP-Auswertung
        └── Python/campaign_runner.py  Hintergrund-Thread (Start/Stop)
```

Zentrale Entscheidung: Die früheren **Standalone-Skripte** (mit Code auf
Modulebene und `while True`-Schleifen) wurden zu **importierbaren Modulen mit
Funktionen** umgebaut, damit der Flask-Server sie direkt aufrufen kann.

---

## 2. Durchgeführte Änderungen

### Neue Dateien
| Datei | Zweck |
|-------|-------|
| `Python/mail_sender.py` | Versand-Engine (aus `MailSender.py` refaktoriert), Dry-Run-fähig, Credentials aus Settings |
| `Python/mail_reader.py` | IMAP-Auswertung (aus `MailRead.py` refaktoriert), als Funktion `check_responses()` |
| `Python/campaign_runner.py` | Hintergrund-Thread-Manager: Kampagne starten/stoppen, Fortschritt verfolgen |
| `UI/HTML/login.html` | Einfache Passwort-Login-Seite |
| `requirements.txt` | Abhängigkeiten (`Flask`, `PyYAML`) |
| `ABSCHLUSSBERICHT.md` | Dieser Bericht |

### Gelöschte Dateien
- `Python/MailSender.py`, `Python/MailRead.py` → ersetzt durch die refaktorierten Module.
- `Server/Flask/test.html`, `Server/Flask/failed_set_status.html`, `UI/HTML/Test.html` → tote/überholte Artefakte.
- `junk/` (kaputtes `generator.py`, ungenutztes HTML).

### Wesentlich geänderte Dateien
- **`Server/Flask/App.py`** – komplett ausgebaut: Login/Logout, Dashboard,
  vollständige JSON-API, öffentliche Tracking-Endpunkte. Status-Bugfix (s.u.).
- **`Server/Flask/config_manager.py`** – jetzt zentrale Pfad-, Config- und
  Settings-Verwaltung inkl. `settings.json` und robustem Fallback auf die erste
  vorhandene YAML.
- **`Python/data_creator.py`** – in `create_campaign_db()` gekapselt; englische
  Statuswerte; neue `campaign_meta`-Tabelle.
- **`UI/HTML/dashboard.html`** – sämtliche Demo-Daten und Dummy-Handler entfernt;
  jeder Button/jedes Formular ruft jetzt eine echte API auf.
- **`Server/Flask/fakeWebsiteBackend.js`** – übergibt Kampagnen-ID, leitet zur
  Aufklärungsseite statt zum Rickroll.
- **`Server/Mails/google.html`** – Tracking-Link nutzt jetzt den Platzhalter `{link}`.
- **`.gitignore`** – ignoriert Laufzeit-Artefakte (DB, `settings.json`, `active_config.txt`).

---

## 3. Neue Funktionen

- **Login/Logout** (session-basiert). Passwort im Klartext in `settings.json`
  (bewusste Projektvorgabe), Standard `admin`.
- **Kampagnen-Verwaltung über die Oberfläche**: erstellen (aus aktiver YAML),
  starten, stoppen, Live-Fortschritt.
- **Hintergrund-Versand** (`campaign_runner`): verteilt die Mail-Wellen gemäß
  YAML-Zeitraum und sendet nur fällige Wellen; per Web start-/stoppbar.
- **Dry-Run-Modus** (Standard an): simuliert Versand/IMAP, ohne echte Mails.
- **Echte Statistik-API**: Diagramme, Nutzertabelle und Detail-Modal werden aus
  der Datenbank gespeist (keine Demo-Daten mehr).
- **CSV-Upload** der Lehrerliste und **YAML-Upload** der Kampagnen-Konfiguration
  – beide schreiben serverseitig.
- **Einstellungs-Oberfläche**: SMTP/IMAP/Absender/Betreff/Tracking-URL/Dry-Run
  und Admin-Passwort werden persistiert. Passwörter werden nie an die GUI
  zurückgegeben; leere Passwortfelder überschreiben gespeicherte Geheimnisse nicht.
- **„Antworten prüfen“** löst die IMAP-Auswertung manuell aus.
- **Aufklärungsseite** (`/awareness`) nach einem Klick auf den Simulationslink.

---

## 4. Angepasste Funktionen / wiederverwendete Logik

- **Filterlogik** der Empfänger (`user_erlaubt` → `user_allowed`) – inhaltlich
  unverändert, nur parameterbasiert statt über globale Variablen.
- **Mail-Verteilung** `verteile_mails` → `build_distribution_plan` – Logik
  übernommen, ergänzt um `waves_due_by()` für die fälligen Wellen.
- **Template-Laden** `declareMailBody` → `load_template`.
- **IMAP-Marker-Erkennung** `mh(\d+)` und DB-Update aus `MailRead.py` übernommen.
- **DB-Nummerierung** `campaign{N}.db` (aus `data_creator`) beibehalten.

---

## 5. Architekturentscheidungen

1. **Status-Werte auf Englisch** (Projektvorgabe): `reported` (gemeldet →
   Erfolg), `clicked` (Link geklickt → durchgefallen), `no_response` (Default).
   Ersetzt `bestanden`/`durchgefallen`/`nicht beantwortet` in DB, Backend und UI.
2. **Logik-Bugfix:** Ein Klick auf den Phishing-Link wird jetzt korrekt als
   `clicked` (durchgefallen) gewertet. Zuvor setzte `/apply` fälschlich
   „bestanden“. Eine gemeldete/weitergeleitete Mail (IMAP) ergibt `reported`.
3. **Kampagne = eine `campaign{N}.db`** mit zusätzlicher `campaign_meta`-Tabelle
   (Name, Zeitraum, Status, Fortschritt) – kein separater Metadaten-Store nötig.
4. **Zentrale `config_manager`-Schicht** als einzige Quelle für Pfade,
   Einstellungen und die aktive Konfiguration; beseitigt die zuvor verstreuten,
   teils fehlerhaften relativen Pfade und die **hartkodierten Gmail-Zugangsdaten**.
5. **Dry-Run als Standard**, damit das System ohne Risiko getestet werden kann;
   echter Versand erst nach bewusster Konfiguration in den Einstellungen.
6. **Bewusst nicht umgesetzt** (auf Wunsch): **kein** CSV-/PDF-Export der
   Statistiken. Auswertungen sind ausschließlich in der Weboberfläche sichtbar.

---

## 6. Installation & Start

```bash
pip install -r requirements.txt
python Server/Flask/App.py        # läuft auf http://127.0.0.1:5000
```

1. `/login` mit Standardpasswort `admin` (danach unter *Profil* ändern).
2. Unter **Daten** eine CSV-Lehrerliste und eine Kampagnen-YAML hochladen.
3. **Create Campaign** → Kampagne im Dropdown wählen → **Kampagne starten**.
4. Ergebnisse unter **Statistiken** (im Dry-Run können Klicks über die
   Tracking-URL `/track?c=<id>&id=<welle>&email=<adresse>` simuliert werden).
5. Für echten Betrieb in **Einstellungen** die SMTP/IMAP-Zugangsdaten setzen und
   **Dry-Run deaktivieren**.

---

## 7. Verifikation

Ein automatisierter End-to-End-Test (Flask-Testclient, Dry-Run) wurde während
der Entwicklung ausgeführt und bestätigte u. a.:
Login/Auth-Schutz, Dashboard-Auslieferung, CSV-Userliste, Kampagne erstellen/
auflisten/starten, vollständiger Wellen-Versand im Dry-Run, Klick-Erfassung via
`/apply` (= `clicked`), korrekte Statistik-Aggregation, Settings-Roundtrip ohne
Passwort-Leak sowie die öffentlichen Tracking-/Aufklärungsseiten.

---

## 8. Offene/empfohlene Erweiterungen (nicht umgesetzt)
- Fortsetzen einer laufenden Kampagne nach Server-Neustart (Persistenz des Threads).
- Mehrere Admin-Konten statt eines gemeinsamen Passworts.
- Härtung für Produktivbetrieb (HTTPS, Passwort-Hashing, CSRF-Schutz).
