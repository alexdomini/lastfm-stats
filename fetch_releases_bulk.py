"""
Fetches release years for every unique (artist, album) pair in the database
that doesn't already have a cached release year.

Can be called programmatically via run(on_progress) or run directly:

    python fetch_releases_bulk.py
"""

import os
import re
import sys
import time
import requests
from dotenv import load_dotenv
import db

load_dotenv()

API_KEY  = os.getenv("LASTFM_API_KEY", "")
API_BASE = "https://ws.audioscrobbler.com/2.0/"


def _get_release_year(artist, album):
    try:
        r = requests.get(API_BASE, params={
            "method":  "album.getInfo",
            "artist":  artist,
            "album":   album,
            "api_key": API_KEY,
            "format":  "json",
        }, timeout=8)
        info = r.json().get("album", {})
        raw  = info.get("wiki", {}).get("published", "") or info.get("releasedate", "")
        if raw:
            m = re.search(r'\b(19|20)\d{2}\b', raw)
            if m:
                return int(m.group())
    except Exception:
        pass
    return None


def run(on_progress=None):
    """
    Fetch release years for all uncached (artist, album) pairs.
    on_progress(done, total, found, message) called after each album.
    """
    if not API_KEY:
        raise RuntimeError("LASTFM_API_KEY must be set in .env")

    db.init_db()
    conn = db.get_conn()

    pairs = conn.execute("""
        SELECT DISTINCT s.artist, s.album
        FROM scrobbles s
        LEFT JOIN album_releases ar ON s.artist = ar.artist AND s.album = ar.album
        WHERE s.album != ''
          AND ar.artist IS NULL
        ORDER BY s.artist, s.album
    """).fetchall()
    conn.close()

    total = len(pairs)
    found = 0

    if on_progress:
        on_progress(0, total, 0, f"{total:,} albums missing release year — starting…")

    for i, row in enumerate(pairs):
        artist, album = row["artist"], row["album"]
        year = _get_release_year(artist, album)
        db.save_album_release(artist, album, year)
        if year:
            found += 1

        if on_progress:
            msg = f"{i+1:,}/{total:,} — {found:,} years found"
            if year:
                msg = f'Found {year}: "{album}" by {artist}'
            on_progress(i + 1, total, found, msg)

        time.sleep(0.22)

    if on_progress:
        on_progress(total, total, found,
                    f"Done. {found:,} release years fetched out of {total:,} albums.")

    return found


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: LASTFM_API_KEY not set in .env")
        sys.exit(1)

    def _print(done, total, found, msg):
        if total:
            pct = int(done / total * 40)
            bar = "█" * pct + "░" * (40 - pct)
            print(f"\r  [{bar}] {msg:<60}", end="", flush=True)
        else:
            print(f"  {msg}")

    count = run(on_progress=_print)
    print(f"\n\n{count:,} release years fetched.")
