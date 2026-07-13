"""
Fetches the country of origin for the top artists in the database
(up to ARTIST_LIMIT by play count) using MusicBrainz artist search.

Can be called programmatically via run(on_progress) or run directly:

    python fetch_artist_countries.py
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv
import db

load_dotenv()

MB_API     = "https://musicbrainz.org/ws/2/"
MB_HEADERS = {"User-Agent": "lastfm-stats/1.0 (alexdomini@gmail.com)"}
ARTIST_LIMIT = 1000


def _get_country(artist_name):
    try:
        r = requests.get(f"{MB_API}artist", params={
            "query": f'artist:"{artist_name}"',
            "fmt":   "json",
            "limit": 1,
        }, headers=MB_HEADERS, timeout=12)
        artists = r.json().get("artists", [])
        if artists:
            return artists[0].get("country")
    except Exception:
        pass
    return None


def run(on_progress=None):
    db.init_db()
    conn = db.get_conn()

    artists = [r[0] for r in conn.execute("""
        SELECT s.artist
        FROM scrobbles s
        LEFT JOIN artist_countries ac ON s.artist = ac.artist
        WHERE ac.artist IS NULL
        GROUP BY s.artist
        ORDER BY COUNT(*) DESC
        LIMIT ?
    """, (ARTIST_LIMIT,)).fetchall()]
    conn.close()

    total = len(artists)
    found = 0
    pending = []

    if on_progress:
        on_progress(0, total, found, f"{total:,} artists to check…")

    for i, artist in enumerate(artists):
        country = _get_country(artist)
        pending.append((artist, country))
        if country:
            found += 1

        if len(pending) >= 50 or i == total - 1:
            now  = int(time.time())
            conn = db.get_conn()
            for a, c in pending:
                conn.execute(
                    "INSERT OR REPLACE INTO artist_countries(artist, country_code, fetched_at) VALUES(?,?,?)",
                    (a, c, now)
                )
            conn.commit()
            conn.close()
            pending = []

        if on_progress:
            msg = f"{i+1:,}/{total:,} — {found:,} countries found"
            if country:
                msg = f"{artist} → {country}"
            on_progress(i + 1, total, found, msg)

        time.sleep(1.1)

    if on_progress:
        on_progress(total, total, found,
                    f"Done. {found:,}/{total:,} artists have country data.")
    return found


if __name__ == "__main__":
    def _print(done, total, found, msg):
        if total:
            pct = int(done / total * 40)
            bar = "█" * pct + "░" * (40 - pct)
            print(f"\r  [{bar}] {msg:<60}", end="", flush=True)
        else:
            print(f"  {msg}")

    count = run(on_progress=_print)
    print(f"\n\n{count:,} artist countries fetched.")
