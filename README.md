# Karaoke Song Finder

Search the KaraFun catalog by genre, singer (male/female), duet vs solo, decade and language.

Open `index.html` in a browser. It works straight from disk, with no server needed.

## Updating the data

```sh
# Re-download the KaraFun catalog (to pick up new songs)
python3 scripts/fetch_catalog.py

# Look up singer gender for the next 500 most popular artists not yet done
python3 scripts/lookup_genders.py

# ...or a bigger batch, or everything left (MusicBrainz allows 1 request/sec, so ~5 hours)
python3 scripts/lookup_genders.py --limit 3000
python3 scripts/lookup_genders.py --all
```

The lookup saves progress as it goes. You can stop it with Ctrl+C at any time, and the next run continues where it left off.

To fix a wrong result, edit the artist's value in `data/artists.json`. The values are `male`, `female`, `mixed`, `group` and `unknown`. Then run `python3 scripts/lookup_genders.py --limit 0` to regenerate `data/artists.js`.

## Files

- `data/catalog.csv`: raw KaraFun download
- `data/songs.json` / `songs.js`: cleaned song list, most popular first
- `data/artists.json` / `artists.js`: artist → singer gender, from [MusicBrainz](https://musicbrainz.org)
