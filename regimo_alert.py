#!/usr/bin/env python3
"""
Regimo Wohnungs-Alarm
=====================
Prueft die Regimo-Trefferseite und meldet neue Inserate per Telegram.

Konfiguration ueber Konstanten unten und zwei Umgebungsvariablen:
  TELEGRAM_BOT_TOKEN   Token deines Telegram-Bots
  TELEGRAM_CHAT_ID     deine Chat-ID

Aufruf:  python regimo_alert.py
"""

import os
import re
import sys
import json
import html
import urllib.request
import urllib.parse

# --------------------------------------------------------------------------
# KONFIGURATION  (hier anpassen)
# --------------------------------------------------------------------------

# Welche Seite soll geprueft werden?
# Regionalseite Zuerich (enthaelt Winterthur) ist kleiner und relevanter
# als die Gruppenseite regimo.ch/treffer.
LIST_URL = "https://regimo-zuerich.ch/mieten/kaufen"

# Ortsfilter: Inserat wird gemeldet, wenn einer dieser Begriffe im Text steht.
# Leere Liste = alle Orte.
PLACE_FILTERS = ["Winterthur", "Zürich"]

# Kategoriefilter: Begriff, der im Inseratstext stehen muss.
# Leerer String = jede Kategorie (auch Parkplatz, Gewerbe).
CATEGORY_FILTER = "Wohnung"

# Datei, in der bereits gesehene Inserate gespeichert werden.
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")

# --------------------------------------------------------------------------
# Interna
# --------------------------------------------------------------------------

DETAIL_MARKER = "mietinteressentendetail"
ID_RE = re.compile(r"(\d{6,})$")          # ID = lange Ziffernfolge am URL-Ende
USER_AGENT = "Mozilla/5.0 (compatible; RegimoAlert/1.0)"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def parse_listings(page_html):
    """Liefert Liste von dicts: {id, url, text}. Parsing ueber das href-Muster,
    daher unabhaengig von CSS-Klassen der Seite."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    listings = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if DETAIL_MARKER not in href:
            continue
        url = urllib.parse.urljoin(LIST_URL, href)
        m = ID_RE.search(url.split("?")[0].rstrip("/"))
        if not m:
            continue
        obj_id = m.group(1)
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            text = a.get("title", "")
        # bei Duplikaten den laengeren (informativeren) Text behalten
        if obj_id not in listings or len(text) > len(listings[obj_id]["text"]):
            listings[obj_id] = {"id": obj_id, "url": url, "text": html.unescape(text)}
    return list(listings.values())


def matches_filters(listing):
    text = listing["text"].lower()
    if CATEGORY_FILTER and CATEGORY_FILTER.lower() not in text:
        return False
    if PLACE_FILTERS:
        if not any(p.lower() in text for p in PLACE_FILTERS):
            return False
    return True


def load_seen():
    if not os.path.exists(STATE_FILE):
        return None          # None = allererster Lauf
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (ValueError, OSError):
        return set()


def save_seen(ids):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=0)


def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT:
        print("WARN: kein Telegram-Token/Chat gesetzt, Ausgabe nur lokal:\n" + message)
        return
    api = "https://api.telegram.org/bot%s/sendMessage" % TG_TOKEN
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false",
    }).encode("utf-8")
    req = urllib.request.Request(api, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def main():
    try:
        page_html = fetch(LIST_URL)
    except Exception as exc:
        print("FEHLER beim Abruf: %s" % exc, file=sys.stderr)
        sys.exit(1)

    listings = parse_listings(page_html)
    relevant = [l for l in listings if matches_filters(l)]
    current_ids = {l["id"] for l in relevant}

    seen = load_seen()

    if seen is None:
        # Erster Lauf: nur Grundzustand speichern, nicht alarmieren.
        save_seen(current_ids)
        send_telegram("Regimo-Alarm ist aktiv. Ueberwache %d passende Inserate."
                      % len(current_ids))
        print("Baseline gespeichert: %d Inserate." % len(current_ids))
        return

    new = [l for l in relevant if l["id"] not in seen]

    for l in new:
        msg = "<b>Neues Inserat bei Regimo</b>\n%s\n%s" % (
            html.escape(l["text"]), l["url"])
        send_telegram(msg)
        print("NEU: %s" % l["url"])

    # Zustand aktualisieren: gesehene IDs zusammenfuehren
    save_seen(seen | current_ids)

    if not new:
        print("Keine neuen Inserate (%d passende ueberwacht)." % len(current_ids))


if __name__ == "__main__":
    main()
