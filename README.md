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

**Für Tests über mehrere Rechner/Netzwerke hinweg** reicht `127.0.0.1` nicht aus — damit
Empfänger auf anderen Geräten den `/click`-Link überhaupt erreichen können, muss der Server auf
einer im Netzwerk erreichbaren Adresse lauschen **und** „Tracking-Basis-URL" unter „Einstellungen"
auf genau diese Adresse zeigen (nicht auf `127.0.0.1`):

```bash
AFISH_HOST=0.0.0.0 AFISH_PORT=5000 python Server/Flask/App.py
```

`AFISH_DEBUG=true` nur für die lokale Entwicklung setzen — im Debug-Modus ist ein interaktiver
Code-Ausführungs-Debugger erreichbar, sobald der Server von außen erreichbar ist, und der
automatische Reloader kann den Hintergrund-Thread (Mail-Versand + Report-Prüfung) unbemerkt
neu starten.

## Ablauf einer Kampagne

1. **Empfänger** (Bereich „Daten"): CSV mit Spalten `name,email,gruppe` hochladen (nur `email` ist Pflicht).
2. **Kampagne konfigurieren**: YAML-Datei nach dem Muster in `Server/Datenbanken/beispiel-kampagne.yaml`
   erstellen und hochladen (Anzahl Mail-Wellen, Zeitraum, verwendete Templates).
3. **Templates** (Bereich „Templates"): vorhandene Szenarien ansehen oder eigene `.html`-Datei
   hinzufügen. Der Dateiname bestimmt die Kategorie (Teil vor dem ersten `-`), z. B.
   `office-login.html` → Kategorie `office`. Der Mail-**Betreff** ist keine Einstellung, sondern
   steht im `<title>`-Tag der jeweiligen Template-Datei — eine neue Datei mit neuem `<title>`
   hochladen genügt, ohne irgendwo anders etwas anpassen zu müssen.
4. **Absenderprofile**: in `Server/Datenbanken/sender_profiles.yaml` pro Kategorie hinterlegt
   (Anzeigename + Absenderadresse). **Vor dem produktiven Einsatz müssen die Platzhalteradressen
   durch echte, für das Projekt autorisierte Absenderadressen ersetzt werden.**
5. **Kampagne starten**: verteilt die Mail-Wellen automatisch über den gewählten Zeitraum.
6. **Auswertung** (Bereich „Statistiken"): Live-Zahlen, Tabelle je Lehrkraft. „Ergebnisse
   herunterladen" lädt zwei Dateien: die ausgewertete Excel-Datei (mit berechneten Quoten) und eine
   rohe CSV mit den unverarbeiteten Zahlen pro Lehrkraft, damit sich die Auswertung bei Bedarf
   unabhängig nachrechnen lässt.
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
vorherigen Klick. Die Prüfung nutzt den Zeitraum, der in der jeweiligen Kampagne selbst hinterlegt
ist (nicht die aktuell "aktive" YAML-Datei), damit sie auch dann korrekt bleibt, wenn zwischendurch
eine andere Kampagne hochgeladen wurde.

### Wenn ein Klick oder eine Meldung nicht ankommt

Beide Fälle scheitern **ohne sichtbaren Fehler für den Absender** — die Seite leitet trotzdem immer
zur Info-Seite weiter bzw. das manuelle Prüfen meldet trotzdem `success`. Im Server-Log (Konsole, in
der `App.py` läuft) steht dafür jeweils eine konkrete Zeile:

- `[click] campaign … has no database` bzw. `token not found` → der Link war veraltet (z. B. weil
  `Python/databases/` zwischen zwei Testläufen gelöscht/zurückgesetzt wurde). Für einen neuen
  Testlauf immer eine frische Kampagne erstellen und den Link aus der **neu** versendeten Mail
  verwenden, nicht eine alte Mail aus einem vorherigen Lauf erneut anklicken.
- `[check_responses] … scanning N message(s)` → zeigt, wie viele Mails im konfigurierten Zeitraum
  überhaupt gefunden wurden; `marker … found but no matching (user, wave) event` → die Referenznummer
  wurde gefunden, aber der Absender/die Welle passt zu keinem Ereignis dieser Kampagne (z. B. weil
  die Meldung eigentlich zu einer anderen, gleichzeitig laufenden Kampagne gehört).
- Ein `/click`-Link funktioniert nur, wenn der Server unter einer für den Empfänger erreichbaren
  Adresse läuft (siehe „Für Tests über mehrere Rechner/Netzwerke hinweg" oben) — `127.0.0.1`
  funktioniert erwartungsgemäß nur auf dem Rechner, auf dem der Server selbst läuft.

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
