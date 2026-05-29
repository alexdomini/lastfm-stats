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


MB_API = "https://musicbrainz.org/ws/2/"
MB_HEADERS = {"User-Agent": "lastfm-stats/1.0 (alexdomini@gmail.com)"}


def _year_from_mb(mbid):
    """Look up first-release-date from MusicBrainz using a release mbid."""
    try:
        r = requests.get(f"{MB_API}release/{mbid}",
                         params={"fmt": "json", "inc": "release-groups"},
                         headers=MB_HEADERS, timeout=12)
        date = r.json().get("release-group", {}).get("first-release-date", "")
        if date:
            return int(date[:4])
    except Exception:
        pass
    return None


def _get_release_year(artist, album):
    """Returns (year, used_musicbrainz). year is None if not found."""
    try:
        r = requests.get(API_BASE, params={
            "method":  "album.getInfo",
            "artist":  artist,
            "album":   album,
            "api_key": API_KEY,
            "format":  "json",
        }, timeout=8)
        info    = r.json().get("album", {})
        summary = info.get("wiki", {}).get("summary", "")
        raw     = info.get("releasedate", "")
        mbid    = info.get("mbid", "")

        # 1. "released … YEAR" in the wiki summary
        m = re.search(r'released\b[^.]{0,60}?\b((?:19|20)\d{2})\b', summary)
        if m:
            return int(m.group(1)), False
        # 2. explicit releasedate field (rarely populated but accurate)
        if raw:
            m = re.search(r'\b((?:19|20)\d{2})\b', raw)
            if m:
                return int(m.group(1)), False
        # 3. MusicBrainz via mbid — catches artists with no Last.fm wiki
        if mbid:
            return _year_from_mb(mbid), True
    except Exception:
        pass
    return None, False


def run(on_progress=None):
    """
    Fetch release years for all uncached (artist, album) pairs.
    on_progress(done, total, found, message) called after each album.
    """
    if not API_KEY:
        raise RuntimeError("LASTFM_API_KEY must be set in .env")

    db.init_db()
    conn = db.get_conn()

    # Fetch all albums (uncached, null, or previously wrong) — MusicBrainz
    # fallback now resolves artists with no Last.fm wiki (e.g. Spanish artists).
    pairs = conn.execute("""
        SELECT DISTINCT artist, album FROM scrobbles
        WHERE album != ''
        ORDER BY artist, album
    """).fetchall()
    conn.close()

    total = len(pairs)
    found = 0

    if on_progress:
        on_progress(0, total, 0, f"{total:,} albums missing release year — starting…")

    for i, row in enumerate(pairs):
        artist, album = row["artist"], row["album"]
        year, used_mb = _get_release_year(artist, album)
        db.save_album_release(artist, album, year)
        if year:
            found += 1

        if on_progress:
            msg = f"{i+1:,}/{total:,} — {found:,} years found"
            if year:
                msg = f'Found {year}: "{album}" by {artist}'
            on_progress(i + 1, total, found, msg)

        # MusicBrainz rate limit is 1 req/s; add extra sleep when it was used
        time.sleep(0.22 + (0.8 if used_mb else 0))

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
