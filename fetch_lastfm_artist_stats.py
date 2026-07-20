"""
Fetches global listener count and playcount for the top artists in the
database (up to ARTIST_LIMIT by play count) using Last.fm artist.getInfo.
Skips artists already present in artist_global_stats.

    python fetch_lastfm_artist_stats.py
"""

import os
import time
import requests
from dotenv import load_dotenv
import db

load_dotenv()

LASTFM_API   = "https://ws.audioscrobbler.com/2.0/"
ARTIST_LIMIT = 500


def _get_stats(artist, api_key):
    try:
        r = requests.get(LASTFM_API, params={
            "method": "artist.getInfo",
            "artist": artist,
            "api_key": api_key,
            "format": "json",
        }, timeout=10)
        a     = r.json().get("artist", {})
        stats = a.get("stats", {})
        return (
            int(stats.get("listeners", 0) or 0),
            int(stats.get("playcount",  0) or 0),
        )
    except Exception:
        pass
    return None, None


def run(on_progress=None):
    db.init_db()
    api_key = os.getenv("LASTFM_API_KEY", "")

    conn = db.get_conn()
    artists = [r[0] for r in conn.execute("""
        SELECT s.artist
        FROM scrobbles s
        LEFT JOIN artist_global_stats ags ON s.artist = ags.artist
        WHERE ags.artist IS NULL
        GROUP BY s.artist
        ORDER BY COUNT(*) DESC
        LIMIT ?
    """, (ARTIST_LIMIT,)).fetchall()]
    conn.close()

    total   = len(artists)
    found   = 0
    pending = []

    if on_progress:
        on_progress(0, total, found, f"{total:,} artists to check…")

    for i, artist in enumerate(artists):
        listeners, playcount = _get_stats(artist, api_key)
        pending.append((artist, listeners, playcount))
        if listeners is not None:
            found += 1

        if len(pending) >= 50 or i == total - 1:
            now  = int(time.time())
            conn = db.get_conn()
            for a, l, p in pending:
                conn.execute(
                    "INSERT OR REPLACE INTO artist_global_stats"
                    "(artist, listeners, playcount, fetched_at) VALUES(?,?,?,?)",
                    (a, l, p, now),
                )
            conn.commit()
            conn.close()
            pending = []

        if on_progress:
            msg = f"{i+1:,}/{total:,} — {found:,} fetched"
            if listeners is not None:
                msg = f"{artist} → {listeners:,} listeners"
            on_progress(i + 1, total, found, msg)

        time.sleep(0.22)

    if on_progress:
        on_progress(total, total, found,
                    f"Done. {found:,}/{total:,} artists fetched.")
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
    print(f"\n\n{count:,} artist stats fetched.")
