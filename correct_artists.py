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
    conn = db.get_conn()
    artists = [r[0] for r in conn.execute(
        "SELECT DISTINCT artist FROM scrobbles ORDER BY artist"
    ).fetchall()]
    conn.close()

    total = len(artists)
    corrections = {}

    if on_progress:
        on_progress(0, total, f"Checking {total:,} unique artists...")

    for i, artist in enumerate(artists):
        corrected = _get_correction(artist)
        if corrected:
            corrections[artist] = corrected

        if on_progress:
            msg = f"{i+1}/{total} — {len(corrections)} corrections found"
            if corrected:
                msg = f'Corrected: "{artist}" -> "{corrected}"'
            on_progress(i + 1, total, msg)

        time.sleep(0.22)

    if corrections:
        conn = db.get_conn()
        for wrong, right in corrections.items():
            conn.execute(
                "UPDATE scrobbles SET artist = ? WHERE artist = ?",
                (right, wrong)
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
