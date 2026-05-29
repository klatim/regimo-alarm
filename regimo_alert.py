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
LIST_URL = "https://regimo-zuerich.ch/mieten/kaufen"

# PLZ-Praefixe fuer "Winterthur und Umgebung".
# "84" deckt Winterthur, das Toesstal und das Weinland ab.
PLZ_PREFIXES = [
    "84",          # Winterthur, Toesstal, Weinland
    "8542", "8543", # Wiesendangen, Bertschikon
    "8307", "8308", # Effretikon, Illnau
    "8311",        # Bruetten
    "8315",        # Lindau, Tagelswangen
    "8330", "8332", # Pfaeffikon ZH, Russikon
    "8352",        # Elsau
]

# Kategoriefilter: Begriff, der im Inseratstext stehen muss.
CATEGORY_FILTER = "Wohnung"

# Nur Mietobjekte (Inserate enthalten dann "CHF/Monat").
RENTAL_ONLY = True

# Datei, in der bereits gesehene Inserate gespeichert werden.
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")

# --------------------------------------------------------------------------
# Interna
# --------------------------------------------------------------------------

DETAIL_MARKER = "mietinteressentendetail"
ID_RE = re.compile(r"(\d{6,})$")
PLZ_RE = re.compile(r"\b(\d{4})\b")
ADDR_RE = re.compile(
    r"^(.+?),\s*(\d{4})\s+(.+?)\s+(?:Wohnung|Haus|Gewerbe|B\u00fcro|Garage|Parkplatz)",
    re.IGNORECASE,
)
AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*m\u00b2")
ROOMS_RE = re.compile(r"m\u00b2\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*Zimmer", re.IGNORECASE)
PRICE_RE = re.compile(r"CHF/Monat\s+([\d']+)")
USER_AGENT = "Mozilla/5.0 (compatible; RegimoAlert/1.0)"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def parse_listings(page_html):
    """Liefert Liste von dicts: {id, url, title, text}."""
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
        title = (a.get("title") or "").strip()
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            text = title
        if obj_id not in listings or len(text) > len(listings[obj_id]["text"]):
            listings[obj_id] = {
                "id": obj_id,
                "url": url,
                "title": html.unescape(title),
                "text": html.unescape(text),
            }
    return list(listings.values())


def matches_filters(listing):
    text = listing["text"].lower()
    if CATEGORY_FILTER and CATEGORY_FILTER.lower() not in text:
        return False
    if RENTAL_ONLY and "monat" not in text:
        return False
    if PLZ_PREFIXES:
        plzs = PLZ_RE.findall(text)
        if not any(p.startswith(pref) for p in plzs for pref in PLZ_PREFIXES):
            return False
    return True


def parse_details(listing):
    """Extrahiert Strasse, PLZ, Ort, Zimmer, Flaeche und Preis aus dem Linktext."""
    title = listing.get("title", "")
    full = listing.get("text", "")
    d = {"title": title, "street": "", "plz": "", "city": "", "m2": "", "rooms": "", "price": ""}
    rest = full[len(title):].lstrip(" -\u2013\u2014").strip() if full.startswith(title) else full
    m = ADDR_RE.match(rest)
    if m:
        d["street"] = m.group(1).strip()
        d["plz"] = m.group(2).strip()
        d["city"] = m.group(3).strip()
    a = AREA_RE.search(full)
    if a:
        d["m2"] = a.group(1)
    r = ROOMS_RE.search(full)
    if r:
        d["rooms"] = r.group(1) or r.group(2)
    p = PRICE_RE.search(full)
    if p:
        d["price"] = p.group(1)
    return d


def format_message(listing):
    d = parse_details(listing)
    lines = []
    if d["title"]:
        lines.append("<b>" + html.escape(d["title"]) + "</b>")
    if d["street"] or d["city"]:
        addr = (d["street"] + ", " + d["plz"] + " " + d["city"]).strip(", ").replace("  ", " ")
        lines.append(html.escape(addr))
    facts = []
    if d["rooms"]:
        facts.append(d["rooms"] + " Zi.")
    if d["m2"]:
        facts.append(d["m2"] + " m\u00b2")
    if d["price"]:
        facts.append("CHF " + d["price"] + "/Mt.")
    if facts:
        lines.append(" \u00b7 ".join(facts))
    lines.append("")
    lines.append(listing["url"])
    return "\n".join(lines)


def load_seen():
    if not os.path.exists(STATE_FILE):
        return None
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
        save_seen(current_ids)
        send_telegram("Regimo-Alarm ist aktiv. Ueberwache %d passende Inserate."
                      % len(current_ids))
        print("Baseline gespeichert: %d Inserate." % len(current_ids))
        return

    new = [l for l in relevant if l["id"] not in seen]

    for l in new:
        send_telegram(format_message(l))
        print("NEU: %s" % l["url"])

    save_seen(seen | current_ids)

    if not new:
        print("Keine neuen Inserate (%d passende ueberwacht)." % len(current_ids))


if __name__ == "__main__":
    main()
