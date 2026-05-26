"""
Downloads all scrobbles from Last.fm into the local SQLite database.
Can be called programmatically via run() or executed directly:

    python fetch.py
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv
import db

load_dotenv()

API_KEY  = os.getenv("LASTFM_API_KEY", "")
USERNAME = os.getenv("LASTFM_USER", "")
API_BASE = "https://ws.audioscrobbler.com/2.0/"
PAGE_SIZE = 200


def _get(params):
    params.update({"api_key": API_KEY, "format": "json"})
    for attempt in range(5):
        try:
            r = requests.get(API_BASE, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def run(on_progress=None):
    """
    Fetch scrobbles and store them in SQLite.
    on_progress(page, total_pages, fetched, message) is called after each page.
    Raises RuntimeError if API key / username are missing.
    """
    if not API_KEY or not USERNAME:
        raise RuntimeError("LASTFM_API_KEY and LASTFM_USER must be set in .env")

    db.init_db()

    conn = db.get_conn()
    latest_ts = conn.execute("SELECT MAX(ts) FROM scrobbles").fetchone()[0] or 0
    conn.close()

    from datetime import datetime, timezone
    since_msg = ""
    if latest_ts:
        dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
        since_msg = f"since {dt.strftime('%Y-%m-%d %H:%M UTC')}"

    if on_progress:
        on_progress(0, 0, 0, f"Connecting to Last.fm… {since_msg}")

    data = _get({
        "method": "user.getRecentTracks",
        "user": USERNAME,
        "limit": PAGE_SIZE,
        "autocorrect": 1,
        "page": 1,
        **({"from": latest_ts + 1} if latest_ts else {}),
    })

    attr         = data["recenttracks"]["@attr"]
    total_pages  = int(attr["totalPages"])
    total_tracks = int(attr["total"])

    if total_tracks == 0:
        if on_progress:
            on_progress(1, 1, 0, "Already up to date.")
        return 0

    if on_progress:
        on_progress(0, total_pages, 0,
                    f"Downloading {total_tracks:,} scrobbles ({total_pages} pages)…")

    fetched = 0
    for page in range(1, total_pages + 1):
        if page > 1:
            data = _get({
                "method": "user.getRecentTracks",
                "user": USERNAME,
                "limit": PAGE_SIZE,
                "autocorrect": 1,
                "page": page,
                **({"from": latest_ts + 1} if latest_ts else {}),
            })

        tracks = data["recenttracks"].get("track", [])
        if not isinstance(tracks, list):
            tracks = [tracks]

        rows = []
        for t in tracks:
            if "@attr" in t and t["@attr"].get("nowplaying"):
                continue
            uts = t.get("date", {}).get("uts")
            if not uts:
                continue
            artist = t.get("artist", {}).get("#text", "") or t.get("artist", "")
            album  = t.get("album",  {}).get("#text", "")
            track  = t.get("name", "")
            if artist and track:
                rows.append((int(uts), artist, album, track))

        if rows:
            db.upsert_scrobbles(rows)
            fetched += len(rows)

        if on_progress:
            on_progress(page, total_pages, fetched,
                        f"Page {page}/{total_pages} — {fetched:,} scrobbles downloaded")

        time.sleep(0.22)

    db.set_meta("last_sync", int(time.time()))
    total_stored = db.count_scrobbles()

    if on_progress:
        on_progress(total_pages, total_pages, fetched,
                    f"Done. {fetched:,} new · {total_stored:,} total")

    return fetched


if __name__ == "__main__":
    def _print(page, total, fetched, msg):
        if total:
            pct = int(page / total * 40)
            bar = "█" * pct + "░" * (40 - pct)
            print(f"\r  [{bar}] {msg}", end="", flush=True)
        else:
            print(f"  {msg}")

    try:
        run(on_progress=_print)
        print()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
