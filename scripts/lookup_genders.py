#!/usr/bin/env python3
"""Look up each artist's gender on MusicBrainz and save to data/artists.js.

Artists are processed in popularity order (by their most popular song).
Results are cached in data/artists.json, so re-running skips artists
that are already done and continues with the next batch.

Each artist gets one of:
  male / female  - a solo person
  mixed          - several people, both male and female (e.g. "A & B")
  group          - a band or group (MusicBrainz doesn't record its singer's gender)
  various        - a soundtrack, film/musical, or compilation (various singers)
  unknown        - no confident match

Usage:
  python3 scripts/lookup_genders.py            # next 500 artists
  python3 scripts/lookup_genders.py --limit 2000
  python3 scripts/lookup_genders.py --all      # everything left (takes hours)
  python3 scripts/lookup_genders.py --retry-unknown   # re-check artists marked unknown
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SONGS_JSON = os.path.join(DATA_DIR, "songs.json")
ARTISTS_JSON = os.path.join(DATA_DIR, "artists.json")
ARTISTS_JS = os.path.join(DATA_DIR, "artists.js")

API = "https://musicbrainz.org/ws/2/artist/"
USER_AGENT = "KaraokeSongSearcher/0.1 (personal project)"
DELAY = 1.1  # MusicBrainz allows 1 request per second
MIN_SCORE = 90
EXACT_MIN_SCORE = 75  # a lower score is fine when the name matches exactly

# Credits that are soundtracks, films, musicals or compilations, not one singer.
VARIOUS_RE = re.compile(
    r"\((?:[^)]*\b(?:film|movie|musical|series|soundtrack|show|cast)\b[^)]*)\)"
    r"|\b(?:the movie|soundtrack|original cast|broadway|musical)\b"
    r"|\b(?:songs|standards)$",
    re.I,
)

# Fixes for artists that MusicBrainz search gets wrong or can't find.
OVERRIDES = {
    "Miley Cyrus": "female",
    "Dirty Dancing": "various",
    "The Bodyguard": "various",
    "The Greatest Showman": "various",
    "Mulan": "various",
    "James Bond": "various",
    "8 Mile": "various",
    "Les Dix Commandements": "various",
}

# KaraFun styles that mark a credit as a soundtrack/musical rather than a singer.
VARIOUS_STYLES = {"Soundtrack", "Musical"}

# Splits "Elton John & Kiki Dee", "X feat. Y", "A, B and C", "A x B"
SPLIT_RE = re.compile(r"\s*(?:&|,|\+|\band\b|\bwith\b|\bx\b|\bvs\.?|\bfeat\.?|\bft\.?|\bfeaturing\b)\s*", re.I)

_last_request = [0.0]


def normalize(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", ascii_name.lower()))
    if key:
        return key
    # Non-Latin names (e.g. "あいみょん") have no ASCII form; compare them as-is.
    return re.sub(r"[\W_]", "", name.casefold())


def variants(name):
    """Spellings to try: as given, without "(...)", "A / B" -> "A/B", without "The",
    and the text inside "(...)" (often the name in its own script, e.g. "Aimyon (あいみょん)")."""
    out = [name]
    no_paren = re.sub(r"\s*\([^)]*\)", "", name).strip()
    inside = re.findall(r"\(([^)]*)\)", name)
    for v in (no_paren, re.sub(r"\s*/\s*", "/", no_paren), re.sub(r"^the\s+", "", no_paren, flags=re.I), *inside):
        if v and v not in out:
            out.append(v)
    return out


def search(name, loose=False):
    """Return the best MusicBrainz artist match for name, or None.

    loose=True searches the words without quotes (finds "Lead Belly" for
    "Leadbelly") and only accepts an exact name/alias match."""
    wait = DELAY - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    clean = name.replace('"', "")
    if loose:
        words = re.sub(r'[+\-&|!(){}\[\]^"~*?:\\/]', " ", clean).split()
        if not words:
            return None
        query = "artist:({})".format(" ".join(words))
    else:
        query = 'artist:"{}"'.format(clean)
    url = API + "?" + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 10})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(7):
        _last_request[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 6:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < 6:
                time.sleep(5 * (attempt + 1))
                continue
            raise

    target = normalize(name)
    # Skip untyped stub entries (e.g. bare aliases); they carry no gender/type.
    artists = [a for a in data.get("artists", []) if a.get("type") or a.get("gender")]
    # Prefer an exact name (or alias) match; fall back to the top result.
    for a in artists:
        if int(a.get("score", 0)) < EXACT_MIN_SCORE:
            break
        names = [a.get("name", "")] + [al.get("name", "") for al in a.get("aliases", []) or []]
        if any(normalize(n) == target for n in names):
            return a
    if loose:
        return None
    return artists[0] if artists and int(artists[0]["score"]) == 100 else None


def classify(artist):
    if artist is None:
        return "unknown"
    kind = (artist.get("type") or "").lower()
    gender = (artist.get("gender") or "").lower()
    if kind == "person" or (not kind and gender):
        if gender in ("male", "female"):
            return gender
        return "unknown"
    if kind in ("group", "orchestra", "choir"):
        return "group"
    return "unknown"


def combine(labels):
    labels = set(labels)
    if labels == {"male"}:
        return "male"
    if labels == {"female"}:
        return "female"
    if {"male", "female"} <= labels:
        return "mixed"
    if labels & {"male", "female", "group"}:
        return "group" if "unknown" not in labels else "unknown"
    return "unknown"


def find(name):
    """Best match for name across its spellings, or None."""
    names = variants(name)
    for v in names:
        match = search(v)
        if match is not None:
            return match
    for v in names[:2]:  # unquoted search for the main spellings only
        match = search(v, loose=True)
        if match is not None:
            return match
    return None


def lookup(name, soundtrack_share=0.0):
    """soundtrack_share: fraction of the artist's KaraFun songs tagged Soundtrack/Musical."""
    if name in OVERRIDES:
        return OVERRIDES[name]
    if VARIOUS_RE.search(name):
        return "various"
    label = None
    match = find(name)
    if match is not None:
        label = classify(match)
    else:
        # Multi-artist credit like "Elton John & Kiki Dee": look up each part.
        parts = [p.strip() for p in SPLIT_RE.split(name) if p.strip()]
        if len(parts) > 1:
            label = combine(classify(find(p)) for p in parts)
    # A film/show title (e.g. "Toy Story") matches no singer, or matches an
    # unrelated band; KaraFun tagging most of its songs Soundtrack gives it away.
    if label not in ("male", "female", "mixed") and soundtrack_share >= 0.5:
        return "various"
    return label or "unknown"


def save(results):
    with open(ARTISTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=0, sort_keys=True)
    with open(ARTISTS_JS, "w", encoding="utf-8") as f:
        f.write("window.ARTIST_GENDERS=" + json.dumps(results, ensure_ascii=False, separators=(",", ":")) + ";\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=500, help="how many new artists to look up (default 500)")
    parser.add_argument("--all", action="store_true", help="look up every remaining artist")
    parser.add_argument("--retry-unknown", action="store_true", help="re-check artists marked unknown, then stop")
    args = parser.parse_args()

    if not os.path.exists(SONGS_JSON):
        sys.exit("Run scripts/fetch_catalog.py first.")
    with open(SONGS_JSON, encoding="utf-8") as f:
        songs = json.load(f)

    results = {}
    if os.path.exists(ARTISTS_JSON):
        with open(ARTISTS_JSON, encoding="utf-8") as f:
            results = json.load(f)

    # Unique artists in popularity order (the CSV is sorted by popularity).
    seen, ordered = set(), []
    total, soundtrack = {}, {}
    for s in songs:
        if not s[2]:
            continue
        if s[2] not in seen:
            seen.add(s[2])
            ordered.append(s[2])
        total[s[2]] = total.get(s[2], 0) + 1
        if VARIOUS_STYLES & set(s[6]):
            soundtrack[s[2]] = soundtrack.get(s[2], 0) + 1

    if args.retry_unknown:
        todo = [a for a in ordered if results.get(a) == "unknown"]
    else:
        todo = [a for a in ordered if a not in results]
    if not args.all and not args.retry_unknown:
        todo = todo[: args.limit]
    print("{} artists total, {} done, looking up {} now.".format(len(ordered), len(results), len(todo)))

    try:
        for i, name in enumerate(todo, 1):
            try:
                results[name] = lookup(name, soundtrack.get(name, 0) / total[name])
            except Exception as e:  # keep going; this artist is retried next run
                print("  ! {}: {}".format(name, e))
                continue
            print("  [{}/{}] {} -> {}".format(i, len(todo), name, results[name]))
            if i % 25 == 0:
                save(results)
    except KeyboardInterrupt:
        print("\nStopped early; progress saved.")
    finally:
        save(results)

    counts = {}
    for name in OVERRIDES:  # keep manual fixes even for artists done earlier
        if name in results:
            results[name] = OVERRIDES[name]
    save(results)
    for v in results.values():
        counts[v] = counts.get(v, 0) + 1
    print("Done. {} of {} artists looked up: {}".format(len(results), len(ordered), counts))


if __name__ == "__main__":
    main()
