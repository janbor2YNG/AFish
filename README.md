# AFish — Phishing-Awareness-Plattform für Lehrer

AFish ist ein Jugend-forscht-Projekt: eine interne, autorisierte Phishing-**Simulations**plattform.
Sie versendet kontrollierte, harmlose Test-Mails an eine vorher freigegebene Liste von Lehrkräften,
zeichnet anonymisiert auf, wer auf den enthaltenen Link klickt bzw. die Mail korrekt meldet, und
wertet das Ergebnis aus (inkl. Excel-Export). Es werden **keine echten Zugangsdaten** abgefragt oder
gespeichert, und es werden **keine fremden Marken- oder Firmendomains** missbraucht.

## Schnellstart

```bash
pip install -r requirements.txt
python Server/Flask/App.py
```

Die App läuft danach standardmäßig unter `http://127.0.0.1:5000` im **Dry-Run-Modus**
(Standardeinstellung `dry_run: true`) — es werden keine echten Mails versendet, alle Aktionen
werden nur protokolliert. Erst wenn SMTP/IMAP-Zugangsdaten unter „Einstellungen" hinterlegt und
Dry-Run deaktiviert wird, verschickt das System tatsächlich Mails.

Login-Passwort initial: `admin` (unter „Einstellungen" → „Profil" sofort ändern).

## Ablauf einer Kampagne

1. **Empfänger** (Bereich „Daten"): CSV mit Spalten `name,email,gruppe` hochladen (nur `email` ist Pflicht).
2. **Kampagne konfigurieren**: YAML-Datei nach dem Muster in `Server/Datenbanken/beispiel-kampagne.yaml`
   erstellen und hochladen (Anzahl Mail-Wellen, Zeitraum, verwendete Templates).
3. **Templates** (Bereich „Templates"): vorhandene Szenarien ansehen oder eigene `.html`-Datei
   hinzufügen. Der Dateiname bestimmt die Kategorie (Teil vor dem ersten `-`), z. B.
   `office-login.html` → Kategorie `office`.
4. **Absenderprofile**: in `Server/Datenbanken/sender_profiles.yaml` pro Kategorie hinterlegt
   (Anzeigename + Absenderadresse). **Vor dem produktiven Einsatz müssen die Platzhalteradressen
   durch echte, für das Projekt autorisierte Absenderadressen ersetzt werden.**
5. **Kampagne starten**: verteilt die Mail-Wellen automatisch über den gewählten Zeitraum.
6. **Auswertung** (Bereich „Statistiken"): Live-Zahlen, Tabelle je Lehrkraft, Excel-Download.
7. **Vergleich** (Bereich „Vergleich"): Klick-/Melderate über mehrere Trainingsdurchgänge hinweg.

## Wie ein Klick erkannt wird

Jede versendete Mail enthält einen Link mit einer zufälligen, einmaligen Kennung
(`/click/<kampagne>/<token>`) — **keine E-Mail-Adresse und kein Name stehen in der URL**. Ein Klick
markiert das Ereignis als „geklickt" und leitet sofort auf eine interne Info-Seite weiter, die
erklärt, woran die Simulation zu erkennen gewesen wäre. Es werden zu keinem Zeitpunkt Zugangsdaten
abgefragt.

## Wie eine Meldung erkannt wird

Leitet eine Lehrkraft die Simulationsmail an die konfigurierte interne Meldeadresse weiter, sucht
das System (per IMAP) im Postfach nach der Referenznummer in der Mail-Fußzeile (`Referenz: TRX-<n>`)
und markiert das zugehörige Ereignis als „korrekt gemeldet" — das gewinnt immer gegenüber einem
vorherigen Klick.

## Betrieb & Datenschutz

Dieses Tool simuliert Phishing-Angriffe. Der Einsatz ist **ausschließlich mit ausdrücklicher
organisatorischer Genehmigung** (Schulleitung, ggf. Datenschutzbeauftragte/r, Personalvertretung)
und gegenüber vorher festgelegten, autorisierten Teilnehmergruppen zulässig.

Vor dem Einsatz sicherstellen:

- **Autorisierung**: schriftliche Freigabe für Zeitraum, Teilnehmerkreis und verwendete Absender-
  domains liegt vor.
- **Keine echten Zugangsdaten**: die Templates fragen zu keinem Zeitpunkt Passwörter oder sonstige
  Zugangsdaten ab; das bleibt auch bei neuen Templates so.
- **Nur autorisierte Domains**: `sender_profiles.yaml` darf ausschließlich Adressen enthalten, die
  dem Projekt/der Schule gehören oder ausdrücklich für die Simulation freigegeben wurden — niemals
  echte fremde Marken- oder Firmendomains.
- **Datenminimierung**: die Empfängerliste enthält nur `name` (optional), `email` (Pflicht) und
  `gruppe` (optional, nur zur Auswertung). Keine zusätzlichen personenbezogenen Daten erheben.
- **Interner Betrieb**: die App läuft auf einem internen Schulserver, nicht öffentlich erreichbar.
  `settings.json`, `active_config.txt` und alle `campaign*.db`-Dateien bleiben lokal und sind bereits
  über `.gitignore` von der Versionskontrolle ausgeschlossen.
- **Zugriffsschutz**: das Admin-Passwort direkt nach der Installation ändern (Bereich „Profil").
  Das Session-Secret wird über die Umgebungsvariable `AFISH_SECRET_KEY` gesetzt (ohne diese wird
  beim Start ein zufälliges, nur für diesen Prozess gültiges Secret erzeugt — Sessions überleben
  dann keinen Neustart, was für den internen Testbetrieb ausreichend, für Dauerbetrieb aber nicht
  empfohlen ist).
- **Zugriff auf Ergebnisse**: nur autorisierte Personen erhalten das Admin-Passwort bzw. Zugriff auf
  die exportierten Excel-Dateien.
- **Kein Versand nach außen**: SMTP/IMAP-Zugangsdaten werden ausschließlich in `settings.json`
  (außerhalb der Versionskontrolle) gespeichert, nie im Quellcode.
