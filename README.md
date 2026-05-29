# Regimo Wohnungs-Alarm

Meldet dir per Telegram sofort, wenn auf Regimo ein neues passendes Inserat erscheint.
Standard: neue **Wohnungen** in **Winterthur** oder **Zürich** auf der Regionalseite
`regimo-zuerich.ch`.

Das Skript prüft die Trefferseite alle fünf Minuten über GitHub Actions. Ein eigener
Server oder ein dauerhaft laufender Rechner ist nicht nötig.

---

## So funktioniert es

1. Das Skript lädt die Trefferseite und liest alle Inserate aus.
2. Es filtert nach Ort und Kategorie.
3. Es vergleicht die gefundenen IDs mit der Datei `seen.json`.
4. Bei einer neuen ID schickt es dir eine Telegram-Nachricht mit Titel und Link.
5. Den ersten Lauf nutzt es nur zum Aufbau der Grundliste, dann bleibt es ruhig.

---

## Einrichtung in vier Schritten

### 1. Telegram-Bot anlegen

1. Öffne in Telegram den Chat mit **@BotFather**.
2. Sende `/newbot` und folge den Schritten. Du erhältst einen **Bot-Token**
   der Form `123456789:ABC...`.
3. Schreibe deinem neuen Bot irgendeine Nachricht (sonst darf er dir nicht antworten).
4. Hole deine **Chat-ID**: Öffne im Browser
   `https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates`
   und suche im JSON nach `"chat":{"id":...}`. Diese Zahl ist deine Chat-ID.

### 2. Repository erstellen

1. Lege auf GitHub ein neues, privates Repository an, zum Beispiel `regimo-alarm`.
2. Lade diese Dateien hinein:
   - `regimo_alert.py`
   - `.github/workflows/check.yml`  (Ordner so anlegen, Datei `check.yml` hinein)

### 3. Zugangsdaten hinterlegen

Im Repository unter **Settings → Secrets and variables → Actions → New repository secret**:

| Name                  | Wert                         |
|-----------------------|------------------------------|
| `TELEGRAM_BOT_TOKEN`  | dein Bot-Token               |
| `TELEGRAM_CHAT_ID`    | deine Chat-ID                |

### 4. Starten

Unter **Actions** den Workflow „Regimo Wohnungs-Alarm" auswählen und einmal
**Run workflow** drücken. Du solltest eine Bestätigung in Telegram erhalten.
Danach läuft die Prüfung automatisch alle fünf Minuten.

---

## Filter anpassen

Oben in `regimo_alert.py`:

```python
LIST_URL = "https://regimo-zuerich.ch/mieten/kaufen"
PLACE_FILTERS = ["Winterthur", "Zürich"]   # leere Liste = alle Orte
CATEGORY_FILTER = "Wohnung"                # leerer String = jede Kategorie
```

Beispiele:
- Nur Winterthur: `PLACE_FILTERS = ["Winterthur"]`
- Ganze Gruppe statt nur Zürich: `LIST_URL = "https://regimo.ch/treffer"`
- Auch Häuser zulassen: `CATEGORY_FILTER = ""` und Ort streng setzen

---

## Grenzen, ehrlich benannt

- Das Skript liest die **erste Trefferseite** (neueste zuerst). Neue Inserate
  erscheinen dort zuerst, daher genügt das in der Praxis. Erscheinen sehr viele
  Inserate gleichzeitig, kann ein Treffer auf eine Folgeseite rutschen. Die
  Prüfung alle fünf Minuten hält dieses Risiko klein.
- GitHub-Actions-Zeitpläne starten gelegentlich ein paar Minuten verspätet.
  Für „möglichst sofort" ist das normalerweise ausreichend.
- Ändert Regimo die Seitenstruktur grundlegend, muss der Parser angepasst werden.
  Da er über das URL-Muster `mietinteressentendetail` arbeitet, ist er gegenüber
  reinen Designänderungen robust.

---

## Lokaler Test

```bash
pip install beautifulsoup4
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python regimo_alert.py
```

Ohne gesetzte Telegram-Variablen gibt das Skript Treffer nur im Terminal aus.
