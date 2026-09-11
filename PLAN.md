# AFish → einfache Phishing-Awareness-Plattform für Lehrer

## Context

AFish ist ein Jugend-forscht-Projekt: eine interne, autorisierte Phishing-Simulationsplattform für Lehrer (kein echter Angriff, keine echte Credential-Abfrage). Der bestehende Code (Flask + SQLite + YAML-Kampagnen + IMAP-Report-Erkennung) ist bereits eine brauchbare, einfache Grundarchitektur und wird **nicht neu geschrieben**, sondern gezielt erweitert/bereinigt. Größte fehlende Funktion: **Excel-Export** — laut Vorgabe die wichtigste Funktion überhaupt, aktuell nicht vorhanden.

Arbeitsweise laut Nutzer:
1. Branches umbauen (`main` → `legacy-code`, neuer `main` ab demselben Stand), das zu `origin` pushen.
2. Diesen Plan als Datei ins Repo committen und per PR einreichen (nur der Plan, kein Code).
3. Die eigentliche Implementierung erfolgt **später** (separater Auftrag/PR), nicht in diesem Durchgang.
4. Ab jetzt grundsätzlich über PRs arbeiten, nicht direkt auf `main` pushen.

Zwei offene Detailfragen wurden vom Nutzer nicht explizit beantwortet — hier die empfohlenen Standardoptionen aus der Rückfrage (zur Bestätigung/Korrektur in der PR-Review):
- **CSV-Schema**: minimal (`name, email, gruppe`), keine Filterung mehr nach Alter/Fach/Rolle.
- **Sender-Profile**: globale Datei (`sender_profiles.yaml`), nicht pro Kampagne dupliziert.

Bestätigt vom Nutzer:
- **Training/Vergleich**: nur ein Durchgangs-Vergleich (Tabelle/Chart über Kampagnen hinweg). Kein In-App-Trainingsmodul — Trainings finden unabhängig von der App durch Menschen statt.
- **Push-Workflow**: Branch-Umbau + Plan-PR jetzt, Implementierung später, danach immer über PRs.

## Zielarchitektur (unverändert zur bestehenden: Flask + SQLite + YAML + IMAP, keine neuen Großkomponenten)

```
Server/Flask/App.py            – Flask-App: Auth, Dashboard, Tracking-Endpunkte, JSON-API (bleibt)
Server/Flask/config_manager.py – Pfade/Settings (bleibt, + SECRET_KEY aus Env, sender_profiles laden)
Python/data_creator.py         – Kampagne aus YAML+CSV anlegen (bleibt, Filterlogik entfernt)
Python/mail_sender.py          – Versand (bleibt, + Sender-Profil pro Template, + Tracking-Token)
Python/mail_reader.py          – IMAP-Report-Erkennung (bleibt, unverändert in der Logik)
Python/campaign_runner.py      – Hintergrund-Thread (bleibt, unverändert)
Python/excel_export.py         – NEU: Kampagnen-Ergebnisse als .xlsx
Server/Mails/*.html            – Templates: test.html → office-login.html, google.html → google-login.html (bereinigt), + schulleitung-formular.html (neu)
Server/Datenbanken/sender_profiles.yaml – NEU: Template → {Anzeigename, Absenderadresse}
UI/HTML/dashboard.html         – + Templates-Tab, + Ergebnisse/Vergleich-Tab, + Excel-Download-Button
UI/HTML/preview.html           – entfernt (Design-System-Demo, keine echte Funktion)
```

## Wichtigste Änderungen im Detail

### 1. Excel-Export (`Python/excel_export.py`, neue Route `GET /api/campaigns/<id>/export.xlsx`)
- `openpyxl` (neue Dependency in `requirements.txt`).
- Sheet "Übersicht": Kennzahl/Wert-Tabelle (Gesamt versendet, pro Template-Kategorie, Klicks, korrekt gemeldet, Erkennungsquote, Klickquote) — Zahlen aus derselben Aggregation, die heute schon `_campaign_stats()` in `App.py` für die Dashboard-Ansicht liefert (wiederverwenden, nicht duplizieren).
- Sheet "Teilnehmerübersicht": eine Zeile pro Lehrer (Name/E-Mail, Anzahl erhalten, geklickt, korrekt gemeldet, pro Kategorie).
- Sheet "Detaildaten": eine Zeile pro Versand-Event (Empfänger, Kampagne, Template, Kategorie, Versandzeitpunkt, Status, Klick-Zeitpunkt, Meldezeitpunkt) — aus den vorhandenen `mail_<n>`-Spalten pro Nutzer entfaltet.
- Button "Excel herunterladen" im bestehenden Ergebnisse-Bereich des Dashboards.

### 2. Tracking-Link ohne E-Mail-Adresse in der URL
- Aktuell: `/track?c=<id>&id=<wave>&email=<email>` — E-Mail steht offen in der URL (Browser-Verlauf, Server-Logs, Proxies).
- Neu: pro versendeter Mail wird ein zufälliges Token erzeugt (`secrets.token_urlsafe`) und in einer schlanken Zusatztabelle `link_tokens(token TEXT PRIMARY KEY, user_id, wave)` je Kampagnen-DB gespeichert (angelegt von `data_creator.create_campaign_db`, befüllt in `mail_sender.send_wave`). Link wird zu `/click/<token>`. `/apply`-Logik (jetzt `/click/<token>`) schlägt den Token nach statt E-Mail+Wave aus dem Query-String zu vertrauen.
- `fakeWebsiteBackend.js` entsprechend anpassen (kein `email`-Query-Param mehr nötig).

### 3. Sender-Profile pro Template
- `Server/Datenbanken/sender_profiles.yaml`:
  ```yaml
  office-login:
    name: "IT-Support"
    email: "office-support@simulation.schule-intern.example"
  google-login:
    name: "Google-Konto Service"
    email: "konto-service@simulation.schule-intern.example"
  schulleitung-formular:
    name: "Schulleitung"
    email: "verwaltung@simulation.schule-intern.example"
  ```
- `config_manager.get_sender_profiles()` lädt die Datei (Default-Fallback: globaler `sender_email` aus `settings.json`, wie heute).
- `mail_sender.send_wave` setzt `From`-Header aus dem Profil des gewählten Templates statt aus den globalen Settings; SMTP-Login bleibt ein einziger technischer Account (kein Multi-Mailbox-Setup nötig).
- Datei ist über die neue Templates-UI lesbar/erweiterbar (Mapping-Tabelle unter der Template-Liste), nicht über die Kampagnen-YAML.

### 4. Templates bereinigen + verwaltbar machen
- `test.html` (Platzhalter-Scherz-Template mit privatem Foto) löschen.
- `google.html` → `google-login.html`: kaputtes quoted-printable-HTML bereinigen, keine externe Bildquelle (Wikipedia) mehr, sauberes minimalistisches Layout, Platzhalter `{name}`, `{link}`.
- Neu: `office-login.html` (Microsoft/Office-Kontoprüfung-Szenario), `schulleitung-formular.html` (angebliche Schulleitungs-Anfrage).
- Neue API `GET /api/templates` (Liste der `.html`-Dateien in `Server/Mails`) und `POST /api/templates/upload` (neue Datei hinzufügen, nur `.html`, einfache Namensvalidierung).
- Dashboard: neuer Tab "Templates" mit Liste + Upload-Formular + Sender-Profil-Zuordnung.

### 5. CSV-Schema minimieren (`current_user_list.csv`, `data_creator.py`)
- Neues Schema: `name,email,gruppe` (nur `email` Pflichtfeld).
- `user_allowed()`-Filterlogik (role/sub1/sub2/min_alter) entfernen; `target`-Block aus der Kampagnen-YAML entfernen — jede Kampagne verschickt an die komplette importierte Liste (Sub-Selektion künftig einfach über eine gefilterte CSV vor dem Upload, nicht als Code-Feature).
- `gruppe` bleibt rein informativ für Auswertung/Anzeige, keine Versandsteuerung.

### 6. Durchgangs-Vergleich (Ergebnisse-Bereich)
- Kein neuer Speicher nötig: jede Kampagne hat schon `campaign_meta` + Klick-/Meldequote via `_campaign_stats()`.
- Neue API `GET /api/campaigns/compare`: Liste aller Kampagnen mit Name, Zeitraum, Klickquote, Melderate, sortiert nach Startdatum.
- Dashboard: einfache Tabelle "Kampagnenvergleich" (+ optional Differenz zur Vorgänger-Kampagne in Prozentpunkten) im Ergebnisse-Bereich.

### 7. Absicherung / Konfiguration
- `app.secret_key` aus Umgebungsvariable (`AFISH_SECRET_KEY`) statt hartcodiertem String; Fallback: zufällig generiert beim Start (mit Warnung im Log, dass Sessions bei Neustart ungültig werden) — kein Secret im Code.
- Admin-Login: einfache Rate-Begrenzung (z. B. kurze Sperre nach 5 Fehlversuchen pro Prozess) ergänzen — bewusst simpel, keine externe Abhängigkeit.
- `README.md` um einen kurzen Abschnitt "Betrieb & Datenschutz" ergänzen: Muss-Voraussetzungen (interne Nutzung, Autorisierung durch Schulleitung/Datenschutzbeauftragten, keine echten Zugangsdaten, Zugriff auf `/` nur für Admins, `settings.json`/`*.db` bleiben lokal und außerhalb der Versionskontrolle — bereits der Fall laut `.gitignore`).

### 8. Aufräumen
- `UI/HTML/preview.html` entfernen (keine Funktion, nur CSS-Showcase).
- `DSC_0374.JPG` entfernen (privates Foto im joke-Template).

## Ausdrücklich NICHT Teil dieses Umbaus
- Kein In-App-Trainingsmodul/Lernseite (laut Nutzer: Trainings laufen unabhängig von der App).
- Keine neue Datenbank-Technologie, kein Microservice, kein Cloud-Hosting.
- Keine Änderung an der IMAP-Report-Erkennung (`mail_reader.py`) — funktioniert bereits wie gewünscht.

## Ablauf dieses Auftrags

**Teil A — erledigt in diesem PR:**
1. `main` lokal umbenannt in `legacy-code` (bewahrt die bisherige Historie unter neuem Namen), neuer `main` ab demselben Stand angelegt.
2. Dieser Plan als `PLAN.md` auf einem eigenen Branch (`docs/simplification-plan`) committet und als PR gegen `main` eingereicht — es wird noch kein Anwendungscode verändert.

**Teil B — später, separater Auftrag:** die Punkte 1–8 oben tatsächlich implementieren, wieder über einen eigenen Feature-Branch + PR (kein Direct-Push auf `main`).

## Verifikation (für Teil B, wenn implementiert wird)
- `python Server/Flask/App.py` (dry-run Default) starten, Login, Kampagne aus YAML anlegen, starten, `campaign_runner` sendet simuliert (Log-Ausgabe statt echtem SMTP).
- `/click/<token>`-Link aus dem Log/DB manuell aufrufen → Status wechselt auf „clicked", `/awareness` wird angezeigt, keine E-Mail mehr in der URL.
- Excel-Export herunterladen, alle 3 Sheets stichprobenartig gegen die Dashboard-Zahlen prüfen.
- Zweite Test-Kampagne anlegen → Kampagnenvergleich zeigt beide Durchgänge nebeneinander.
