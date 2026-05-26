import os
import threading
import time
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import db

load_dotenv()
app = Flask(__name__)
USERNAME = os.getenv("LASTFM_USER", "")

# ── sync state (shared between background thread and Flask) ───────────────
_sync = {
    "running": False,
    "page": 0,
    "total": 0,
    "fetched": 0,
    "message": "",
    "error": "",
}
_correct = {
    "running": False,
    "done": 0,
    "total": 0,
    "message": "",
    "error": "",
}
_sync_lock = threading.Lock()


def _ts(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


# ── pages ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    db.init_db()
    years = db.available_years()
    ov    = db.overview()
    first = ""
    if ov["first"]:
        first = datetime.fromtimestamp(ov["first"], tz=timezone.utc).strftime("%B %Y")
    last_sync = db.get_meta("last_sync")
    if last_sync:
        last_sync = datetime.fromtimestamp(int(last_sync), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return render_template("index.html",
                           username=USERNAME,
                           years=years,
                           overview=ov,
                           first=first,
                           last_sync=last_sync)


# ── sync endpoints ────────────────────────────────────────────────────────

@app.route("/api/sync", methods=["POST"])
def api_sync_start():
    with _sync_lock:
        if _sync["running"]:
            return jsonify({"ok": False, "error": "A sync is already running."})
        _sync.update(running=True, page=0, total=0, fetched=0, message="Starting…", error="")

    def _run():
        import fetch
        try:
            def on_progress(page, total, fetched, message):
                with _sync_lock:
                    _sync.update(page=page, total=total, fetched=fetched, message=message)
            fetch.run(on_progress=on_progress)
        except Exception as e:
            with _sync_lock:
                _sync["error"] = str(e)
        finally:
            with _sync_lock:
                _sync["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/sync/status")
def api_sync_status():
    with _sync_lock:
        state = dict(_sync)
    last_sync = db.get_meta("last_sync")
    if last_sync:
        state["last_sync"] = datetime.fromtimestamp(int(last_sync), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return jsonify(state)


@app.route("/api/correct-artists", methods=["POST"])
def api_correct_start():
    with _sync_lock:
        if _correct["running"] or _sync["running"]:
            return jsonify({"ok": False, "error": "An operation is already running."})
        _correct.update(running=True, done=0, total=0, message="Loading artists...", error="")

    def _run():
        import correct_artists
        try:
            def on_progress(done, total, message):
                with _sync_lock:
                    _correct.update(done=done, total=total, message=message)
            correct_artists.run(on_progress=on_progress)
        except Exception as e:
            with _sync_lock:
                _correct["error"] = str(e)
        finally:
            with _sync_lock:
                _correct["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/correct-artists/status")
def api_correct_status():
    with _sync_lock:
        return jsonify(dict(_correct))


# ── data endpoints ────────────────────────────────────────────────────────

@app.route("/api/scrobbles-per-month")
def api_scrobbles_per_month():
    return jsonify(db.scrobbles_per_month(year=request.args.get("year")))


@app.route("/api/scrobbles-per-year")
def api_scrobbles_per_year():
    return jsonify(db.scrobbles_per_year())


@app.route("/api/top-artists")
def api_top_artists():
    limit   = int(request.args.get("limit", 20))
    ts_from = _ts(request.args.get("from"))
    ts_to   = _ts(request.args.get("to"))
    return jsonify(db.top_artists(limit=limit, ts_from=ts_from, ts_to=ts_to))


@app.route("/api/top-albums")
def api_top_albums():
    limit   = int(request.args.get("limit", 20))
    ts_from = _ts(request.args.get("from"))
    ts_to   = _ts(request.args.get("to"))
    return jsonify(db.top_albums(limit=limit, ts_from=ts_from, ts_to=ts_to))


@app.route("/api/top-artists-deep")
def api_top_artists_deep():
    limit      = int(request.args.get("limit", 20))
    min_tracks = int(request.args.get("min_tracks", 10))
    ts_from    = _ts(request.args.get("from"))
    ts_to      = _ts(request.args.get("to"))
    return jsonify(db.top_artists_deep(limit=limit, min_tracks=min_tracks,
                                       ts_from=ts_from, ts_to=ts_to))


@app.route("/api/top-albums-deep")
def api_top_albums_deep():
    limit      = int(request.args.get("limit", 20))
    min_tracks = int(request.args.get("min_tracks", 5))
    ts_from    = _ts(request.args.get("from"))
    ts_to      = _ts(request.args.get("to"))
    return jsonify(db.top_albums_deep(limit=limit, min_tracks=min_tracks,
                                      ts_from=ts_from, ts_to=ts_to))


@app.route("/api/top-tracks")
def api_top_tracks():
    limit   = int(request.args.get("limit", 20))
    ts_from = _ts(request.args.get("from"))
    ts_to   = _ts(request.args.get("to"))
    return jsonify(db.top_tracks(limit=limit, ts_from=ts_from, ts_to=ts_to))


@app.route("/api/new-artists")
def api_new_artists():
    limit   = int(request.args.get("limit", 20))
    ts_from = _ts(request.args.get("from"))
    ts_to   = _ts(request.args.get("to"))
    return jsonify(db.new_artists(limit=limit, ts_from=ts_from, ts_to=ts_to))


@app.route("/api/heatmap")
def api_heatmap():
    return jsonify({"hours": db.heatmap_hour(), "weekdays": db.heatmap_weekday()})


@app.route("/api/trending")
def api_trending():
    granularity = request.args.get("g", "month")
    if granularity not in ("week", "month", "year"):
        granularity = "month"
    n_periods = {"week": 12, "month": 12, "year": 6}[granularity]
    min_active = {"week": 3,  "month": 4,  "year": 3}[granularity]
    data = db.trending_artists(granularity=granularity,
                               n_periods=n_periods,
                               min_active_periods=min_active)
    # strip full plays series to last 8 periods for sparkline
    for d in data:
        d['spark'] = d['plays'][-8:]
        del d['plays']
        del d['periods']
    return jsonify(data)


@app.route("/api/artist")
def api_artist():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    profile = db.get_artist_profile(name)
    # convert timestamps to readable strings
    from datetime import datetime, timezone
    if profile["first_ts"]:
        profile["first_date"] = datetime.fromtimestamp(
            profile["first_ts"], tz=timezone.utc).strftime("%d %b %Y")
    return jsonify(profile)


@app.route("/api/fetch-releases", methods=["POST"])
def api_fetch_releases():
    """Fetch release years for a list of albums from Last.fm and cache them."""
    import requests as req
    data   = request.json or {}
    artist = data.get("artist", "")
    albums = data.get("albums", [])
    api_key = os.getenv("LASTFM_API_KEY", "")
    results = {}
    for album in albums[:30]:   # cap per call to avoid long waits
        try:
            r = req.get("https://ws.audioscrobbler.com/2.0/", params={
                "method": "album.getInfo",
                "artist": artist,
                "album":  album,
                "api_key": api_key,
                "format": "json",
            }, timeout=8)
            info = r.json().get("album", {})
            raw  = info.get("wiki", {}).get("published", "") or \
                   info.get("releasedate", "")
            year = None
            if raw:
                import re
                m = re.search(r'\b(19|20)\d{2}\b', raw)
                if m:
                    year = int(m.group())
            db.save_album_release(artist, album, year)
            results[album] = year
        except Exception:
            pass
        time.sleep(0.22)
    return jsonify(results)


@app.route("/api/overview")
def api_overview():
    ov = db.overview()
    if ov["first"]:
        ov["first_str"] = datetime.fromtimestamp(ov["first"], tz=timezone.utc).strftime("%B %Y")
    return jsonify(ov)


if __name__ == "__main__":
    db.init_db()
    print(f"\n  Last.fm Stats -> http://127.0.0.1:5000\n")
    app.run(debug=False, port=5000)
