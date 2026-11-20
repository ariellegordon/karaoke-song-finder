#!/usr/bin/env python3
"""Download the KaraFun catalog CSV and convert it to data/songs.js.

The CSV is sorted by popularity, so each song's position in the output
doubles as its popularity rank.

Usage: python3 scripts/fetch_catalog.py
"""
import csv
import io
import json
import os
import ssl
import urllib.request

CATALOG_URL = "https://www.karafun.com/cl/3107312/2810f075c85dd3b0d5403ba9d2f613fb/"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RAW_CSV = os.path.join(DATA_DIR, "catalog.csv")
SONGS_JSON = os.path.join(DATA_DIR, "songs.json")
SONGS_JS = os.path.join(DATA_DIR, "songs.js")


def download():
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "KaraokeSongSearcher/0.1"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError):
            raise SystemExit(
                "SSL certificate error. If you use python.org's Python, run "
                "'Install Certificates.command' from its Applications folder."
            )
        raise
    with resp:
        return resp.read().decode("utf-8-sig")


def split_list(value):
    return [v.strip() for v in value.split(",") if v.strip()]


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("Downloading catalog...")
    text = download()
    with open(RAW_CSV, "w", encoding="utf-8") as f:
        f.write(text)

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    songs = []
    for row in reader:
        if not row.get("Title"):
            continue
        # Compact array form keeps the file small:
        # [id, title, artist, year, duet, explicit, styles, languages]
        songs.append([
            to_int(row.get("Id")),
            row["Title"].strip(),
            (row.get("Artist") or "").strip(),
            to_int(row.get("Year")),
            1 if row.get("Duo") == "1" else 0,
            1 if row.get("Explicit") == "1" else 0,
            split_list(row.get("Styles") or ""),
            split_list(row.get("Languages") or ""),
        ])

    payload = json.dumps(songs, ensure_ascii=False, separators=(",", ":"))
    with open(SONGS_JSON, "w", encoding="utf-8") as f:
        f.write(payload)
    # A .js wrapper lets index.html open straight from disk (no web server).
    with open(SONGS_JS, "w", encoding="utf-8") as f:
        f.write("window.SONGS=" + payload + ";\n")

    artists = len({s[2] for s in songs})
    print("Saved {} songs by {} artists to {}".format(len(songs), artists, SONGS_JS))


if __name__ == "__main__":
    main()
