"""
Queries Last.fm's artist.getCorrection for every unique artist in the database
and updates rows whose name differs from the canonical form.

Can be called programmatically via run(on_progress) or run directly:

    python correct_artists.py
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv
import db

load_dotenv()

API_KEY  = os.getenv("LASTFM_API_KEY", "")
API_BASE = "https://ws.audioscrobbler.com/2.0/"


def _get_correction(artist_name):
    try:
        r = requests.get(API_BASE, params={
            "method": "artist.getCorrection",
            "artist": artist_name,
            "api_key": API_KEY,
            "format": "json",
        }, timeout=10)
        data = r.json()
        correction = (data.get("corrections") or {}).get("correction")
        if not correction:
            return None
        corrected = (correction.get("artist") or {}).get("name")
        if corrected and corrected.lower() != artist_name.lower():
            return corrected
    except Exception:
        pass
    return None


def run(on_progress=None):
    db.init_db()

    # Re-apply all previously discovered corrections to catch new syncs
    conn = db.get_conn()
    conn.execute("""
        UPDATE scrobbles
        SET artist = (SELECT ac.right FROM artist_corrections ac WHERE ac.wrong = scrobbles.artist)
        WHERE artist IN (SELECT wrong FROM artist_corrections)
    """)
    conn.commit()
    conn.close()

    conn = db.get_conn()
    artists = [r[0] for r in conn.execute("""
        SELECT DISTINCT s.artist FROM scrobbles s
        LEFT JOIN checked_artists ca ON s.artist = ca.artist
        WHERE ca.artist IS NULL
        ORDER BY s.artist
    """).fetchall()]
    conn.close()

    total = len(artists)
    corrections = {}

    if on_progress:
        on_progress(0, total, f"Checking {total:,} unique artists...")

    now = int(time.time())
    checked = []
    for i, artist in enumerate(artists):
        corrected = _get_correction(artist)
        if corrected:
            corrections[artist] = corrected
        checked.append(artist)

        if on_progress:
            msg = f"{i+1}/{total} — {len(corrections)} corrections found"
            if corrected:
                msg = f'Corrected: "{artist}" -> "{corrected}"'
            on_progress(i + 1, total, msg)

        time.sleep(0.22)

    conn = db.get_conn()
    for artist in checked:
        conn.execute(
            "INSERT OR IGNORE INTO checked_artists(artist, checked_at) VALUES(?, ?)",
            (artist, now)
        )
    for wrong, right in corrections.items():
        conn.execute(
            "UPDATE scrobbles SET artist = ? WHERE artist = ?",
            (right, wrong)
        )
        conn.execute(
            "INSERT OR REPLACE INTO artist_corrections(wrong, right, corrected_at) VALUES(?, ?, ?)",
            (wrong, right, now)
        )
        # Remove "wrong" from checked_artists so future syncs can re-apply the correction
        conn.execute("DELETE FROM checked_artists WHERE artist = ?", (wrong,))
        conn.execute(
            "INSERT OR IGNORE INTO checked_artists(artist, checked_at) VALUES(?, ?)",
            (right, now)
        )
    conn.commit()
    conn.close()

    if on_progress:
        on_progress(total, total,
                    f"Done. {len(corrections)} artist names corrected in the database.")

    return corrections


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: LASTFM_API_KEY not set in .env")
        sys.exit(1)

    found = {}

    def _print(done, total, msg):
        if total:
            pct = int(done / total * 40)
            bar = "X" * pct + "." * (40 - pct)
            print(f"\r  [{bar}] {msg:<50}", end="", flush=True)

    found = run(on_progress=_print)
    print(f"\n\n{len(found)} corrections applied.")
