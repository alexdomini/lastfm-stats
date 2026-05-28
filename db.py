import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scrobbles (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        INTEGER NOT NULL,
            artist    TEXT NOT NULL,
            album     TEXT,
            track     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ts     ON scrobbles(ts);
        CREATE INDEX IF NOT EXISTS idx_artist ON scrobbles(artist);
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS album_releases (
            artist      TEXT NOT NULL,
            album       TEXT NOT NULL,
            release_year INTEGER,
            fetched_at  INTEGER NOT NULL,
            PRIMARY KEY (artist, album)
        );
    """)
    conn.commit()
    conn.close()


def get_meta(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_meta(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, str(value)))
    conn.commit()
    conn.close()


def upsert_scrobbles(rows):
    """rows: list of (ts, artist, album, track)"""
    conn = get_conn()
    conn.executemany(
        "INSERT OR IGNORE INTO scrobbles(ts, artist, album, track) VALUES(?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def count_scrobbles():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM scrobbles").fetchone()[0]
    conn.close()
    return n


# ── queries used by the Flask app ──────────────────────────────────────────

def scrobbles_per_month(year=None):
    conn = get_conn()
    if year:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', ts, 'unixepoch') AS month, COUNT(*) AS n
            FROM scrobbles
            WHERE strftime('%Y', ts, 'unixepoch') = ?
            GROUP BY month ORDER BY month
        """, (str(year),)).fetchall()
    else:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', ts, 'unixepoch') AS month, COUNT(*) AS n
            FROM scrobbles GROUP BY month ORDER BY month
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def scrobbles_per_year():
    conn = get_conn()
    rows = conn.execute("""
        SELECT strftime('%Y', ts, 'unixepoch') AS year, COUNT(*) AS n
        FROM scrobbles GROUP BY year ORDER BY year
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def top_artists(limit=20, ts_from=None, ts_to=None):
    conn = get_conn()
    where, params = _ts_filter(ts_from, ts_to)
    rows = conn.execute(f"""
        SELECT artist, COUNT(*) AS n FROM scrobbles
        {where} GROUP BY artist ORDER BY n DESC LIMIT ?
    """, (*params, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def top_albums(limit=20, ts_from=None, ts_to=None):
    conn = get_conn()
    where, params = _ts_filter(ts_from, ts_to)
    rows = conn.execute(f"""
        SELECT artist, album, COUNT(*) AS n FROM scrobbles
        WHERE album != '' {('AND ' + where[6:]) if where else ''}
        GROUP BY artist, album ORDER BY n DESC LIMIT ?
    """, (*params, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def top_artists_deep(limit=20, min_tracks=10, ts_from=None, ts_to=None):
    """Artists ranked by geometric mean of plays per unique track."""
    import math
    from collections import defaultdict
    conn = get_conn()
    where, params = _ts_filter(ts_from, ts_to)
    rows = conn.execute(f"""
        SELECT artist, track, COUNT(*) AS plays
        FROM scrobbles
        {where}
        GROUP BY artist, track
    """, params).fetchall()
    conn.close()

    artists = defaultdict(list)
    for r in rows:
        artists[r["artist"]].append(r["plays"])

    results = []
    for artist, plays_list in artists.items():
        if len(plays_list) < min_tracks:
            continue
        geo_mean = math.exp(sum(math.log(p) for p in plays_list) / len(plays_list))
        results.append({
            "artist":        artist,
            "score":         round(geo_mean, 1),
            "unique_tracks": len(plays_list),
            "total_plays":   sum(plays_list),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def top_albums_deep(limit=20, min_tracks=5, ts_from=None, ts_to=None):
    """Albums ranked by geometric mean of plays per unique track.
    Penalizes albums dominated by a single song."""
    import math
    from collections import defaultdict
    conn = get_conn()
    where, params = _ts_filter(ts_from, ts_to)
    rows = conn.execute(f"""
        SELECT artist, album, track, COUNT(*) AS plays
        FROM scrobbles
        WHERE album != '' {('AND ' + where[6:]) if where else ''}
        GROUP BY artist, album, track
    """, params).fetchall()
    conn.close()

    albums = defaultdict(list)
    for r in rows:
        albums[(r["artist"], r["album"])].append(r["plays"])

    results = []
    for (artist, album), plays_list in albums.items():
        if len(plays_list) < min_tracks:
            continue
        geo_mean = math.exp(sum(math.log(p) for p in plays_list) / len(plays_list))
        results.append({
            "artist":        artist,
            "album":         album,
            "score":         round(geo_mean, 1),
            "unique_tracks": len(plays_list),
            "total_plays":   sum(plays_list),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def top_tracks(limit=20, ts_from=None, ts_to=None):
    conn = get_conn()
    where, params = _ts_filter(ts_from, ts_to)
    rows = conn.execute(f"""
        SELECT artist, track, COUNT(*) AS n FROM scrobbles
        {where} GROUP BY artist, track ORDER BY n DESC LIMIT ?
    """, (*params, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def heatmap_hour():
    conn = get_conn()
    rows = conn.execute("""
        SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER) AS hour,
               COUNT(*) AS n
        FROM scrobbles GROUP BY hour ORDER BY hour
    """).fetchall()
    conn.close()
    data = {r["hour"]: r["n"] for r in rows}
    return [data.get(h, 0) for h in range(24)]


def new_artists(limit=20, ts_from=None, ts_to=None):
    """Artists whose very first scrobble ever falls within the given range."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.artist, COUNT(*) AS n
        FROM scrobbles s
        WHERE s.ts >= ? AND s.ts <= ?
          AND s.artist IN (
              SELECT artist FROM scrobbles
              GROUP BY artist
              HAVING MIN(ts) >= ? AND MIN(ts) <= ?
          )
        GROUP BY s.artist
        ORDER BY n DESC
        LIMIT ?
    """, (ts_from, ts_to, ts_from, ts_to, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def heatmap_weekday():
    conn = get_conn()
    # strftime %w: 0=Sunday
    rows = conn.execute("""
        SELECT CAST(strftime('%w', ts, 'unixepoch', 'localtime') AS INTEGER) AS dow,
               COUNT(*) AS n
        FROM scrobbles GROUP BY dow ORDER BY dow
    """).fetchall()
    conn.close()
    data = {r["dow"]: r["n"] for r in rows}
    # reorder Sun=0 → Mon=0
    order = [1, 2, 3, 4, 5, 6, 0]
    return [data.get(d, 0) for d in order]


def available_years():
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', ts, 'unixepoch') AS y
        FROM scrobbles ORDER BY y DESC
    """).fetchall()
    conn.close()
    return [r["y"] for r in rows]


def overview():
    conn = get_conn()
    total   = conn.execute("SELECT COUNT(*) FROM scrobbles").fetchone()[0]
    artists = conn.execute("SELECT COUNT(DISTINCT artist) FROM scrobbles").fetchone()[0]
    albums  = conn.execute("SELECT COUNT(DISTINCT album) FROM scrobbles WHERE album!=''").fetchone()[0]
    tracks  = conn.execute("SELECT COUNT(DISTINCT track||'|'||artist) FROM scrobbles").fetchone()[0]
    first   = conn.execute("SELECT MIN(ts) FROM scrobbles").fetchone()[0]
    conn.close()
    return dict(total=total, artists=artists, albums=albums, tracks=tracks, first=first)


def trending_artists(granularity='month', n_periods=12, limit=20, min_active_periods=4):
    """
    Artists with a sustained upward trend in play count.
    Uses linear regression slope normalised by the artist's mean plays,
    so a small artist growing fast can outrank a big one growing slowly.

    granularity : 'week' | 'month' | 'year'
    n_periods   : how many periods to look back
    min_active_periods : artist must have plays in at least this many periods
    """
    import time
    from collections import defaultdict

    now_ts = int(time.time())
    seconds = {'week': 7*86400, 'month': 30*86400, 'year': 365*86400}
    fmt     = {'week': '%Y-%W',  'month': '%Y-%m',   'year': '%Y'}
    cutoff  = now_ts - n_periods * seconds[granularity]

    conn = get_conn()
    rows = conn.execute(f"""
        SELECT artist,
               strftime('{fmt[granularity]}', ts, 'unixepoch') AS period,
               COUNT(*) AS n
        FROM scrobbles
        WHERE ts >= ?
        GROUP BY artist, period
    """, (cutoff,)).fetchall()
    conn.close()

    by_artist = defaultdict(dict)
    all_periods = set()
    for r in rows:
        by_artist[r['artist']][r['period']] = r['n']
        all_periods.add(r['period'])

    periods = sorted(all_periods)[-n_periods:]
    n = len(periods)
    if n < 3:
        return []

    mean_x = (n - 1) / 2
    var_x  = sum((i - mean_x) ** 2 for i in range(n))

    results = []
    for artist, pdata in by_artist.items():
        plays = [pdata.get(p, 0) for p in periods]

        if sum(1 for p in plays if p > 0) < min_active_periods:
            continue

        mean_y = sum(plays) / n
        if mean_y < 1:
            continue

        # linear regression slope
        cov_xy = sum((i - mean_x) * (plays[i] - mean_y) for i in range(n))
        slope  = cov_xy / var_x

        if slope <= 0:
            continue

        # normalised: growth per period as % of average
        rel_pct = round(slope / mean_y * 100, 1)

        results.append({
            'artist':     artist,
            'slope':      round(slope, 2),
            'rel_pct':    rel_pct,
            'mean_plays': round(mean_y, 1),
            'total':      sum(plays),
            'plays':      plays,        # full series for sparkline
            'periods':    periods,
        })

    results.sort(key=lambda x: x['rel_pct'], reverse=True)
    return results[:limit]


def get_artist_profile(artist):
    """Full profile data for the artist detail modal."""
    import math
    from collections import defaultdict

    conn = get_conn()

    # basic stats
    row = conn.execute("""
        SELECT COUNT(*) AS total_plays,
               COUNT(DISTINCT track) AS unique_tracks,
               COUNT(DISTINCT album) AS unique_albums,
               MIN(ts) AS first_ts,
               MAX(ts) AS last_ts
        FROM scrobbles WHERE artist = ?
    """, (artist,)).fetchone()

    # top tracks
    top_tracks = [dict(r) for r in conn.execute("""
        SELECT track, COUNT(*) AS n FROM scrobbles
        WHERE artist = ? GROUP BY track ORDER BY n DESC LIMIT 10
    """, (artist,)).fetchall()]

    # per-album per-track plays (for smart scoring)
    album_tracks = conn.execute("""
        SELECT album, track, COUNT(*) AS plays FROM scrobbles
        WHERE artist = ? AND album != ''
        GROUP BY album, track
    """, (artist,)).fetchall()

    # scrobbles per month (last 36 months)
    monthly = [dict(r) for r in conn.execute("""
        SELECT strftime('%Y-%m', ts, 'unixepoch') AS month, COUNT(*) AS n
        FROM scrobbles WHERE artist = ?
        GROUP BY month ORDER BY month DESC LIMIT 36
    """, (artist,)).fetchall()]
    monthly.reverse()

    # cached release years
    cached = {r["album"]: r["release_year"] for r in conn.execute(
        "SELECT album, release_year FROM album_releases WHERE artist = ?",
        (artist,)
    ).fetchall()}

    conn.close()

    # build album smart scores
    by_album = defaultdict(list)
    for r in album_tracks:
        by_album[r["album"]].append(r["plays"])

    today_days = __import__("time").time() / 86400
    albums_scored = []
    for album, plays_list in by_album.items():
        if len(plays_list) < 2:
            continue
        geo_mean = math.exp(sum(math.log(p) for p in plays_list) / len(plays_list))
        total    = sum(plays_list)
        year     = cached.get(album)
        if year:
            release_days = (year - 1970) * 365.25   # approx days since epoch
            age_days     = max(today_days - release_days, 30)
            plays_per_month = total / (age_days / 30)
            smart_score  = round(geo_mean * math.log10(plays_per_month + 1), 2)
            age_label    = f"{year}"
        else:
            smart_score = None
            age_label   = None
        albums_scored.append({
            "album":         album,
            "unique_tracks": len(plays_list),
            "total_plays":   total,
            "geo_mean":      round(geo_mean, 1),
            "smart_score":   smart_score,
            "release_year":  year,
            "age_label":     age_label,
        })

    # sort: prefer smart_score if available, else geo_mean
    albums_scored.sort(
        key=lambda x: x["smart_score"] if x["smart_score"] is not None else x["geo_mean"],
        reverse=True
    )

    # which albums still need release year fetched
    all_albums   = list(by_album.keys())
    missing_years = [a for a in all_albums if a not in cached]

    return {
        "artist":        artist,
        "total_plays":   row["total_plays"],
        "unique_tracks": row["unique_tracks"],
        "unique_albums": row["unique_albums"],
        "first_ts":      row["first_ts"],
        "last_ts":       row["last_ts"],
        "top_tracks":    top_tracks,
        "albums":        albums_scored[:10],
        "monthly":       monthly,
        "missing_years": missing_years,
    }


def save_album_release(artist, album, year):
    import time as _time
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO album_releases(artist, album, release_year, fetched_at)
        VALUES (?, ?, ?, ?)
    """, (artist, album, year, int(_time.time())))
    conn.commit()
    conn.close()


def top_by_decade(decade, limit=10):
    """Top tracks, artists, and albums whose album release year falls in the given decade."""
    conn = get_conn()
    decade_from = decade
    decade_to   = decade + 9

    tracks = conn.execute("""
        SELECT s.artist, s.track, COUNT(*) AS n
        FROM scrobbles s
        JOIN album_releases ar ON s.artist = ar.artist AND s.album = ar.album
        WHERE ar.release_year BETWEEN ? AND ?
        GROUP BY s.artist, s.track
        ORDER BY n DESC LIMIT ?
    """, (decade_from, decade_to, limit)).fetchall()

    artists = conn.execute("""
        SELECT s.artist, COUNT(*) AS n
        FROM scrobbles s
        JOIN album_releases ar ON s.artist = ar.artist AND s.album = ar.album
        WHERE ar.release_year BETWEEN ? AND ?
        GROUP BY s.artist
        ORDER BY n DESC LIMIT ?
    """, (decade_from, decade_to, limit)).fetchall()

    albums = conn.execute("""
        SELECT s.artist, s.album, ar.release_year, COUNT(*) AS n
        FROM scrobbles s
        JOIN album_releases ar ON s.artist = ar.artist AND s.album = ar.album
        WHERE ar.release_year BETWEEN ? AND ?
        GROUP BY s.artist, s.album
        ORDER BY n DESC LIMIT ?
    """, (decade_from, decade_to, limit)).fetchall()

    classified = conn.execute("""
        SELECT COUNT(*) FROM scrobbles s
        JOIN album_releases ar ON s.artist = ar.artist AND s.album = ar.album
        WHERE ar.release_year IS NOT NULL
    """).fetchone()[0]

    total = conn.execute("SELECT COUNT(*) FROM scrobbles").fetchone()[0]
    conn.close()

    return {
        "decade": decade,
        "tracks":  [dict(r) for r in tracks],
        "artists": [dict(r) for r in artists],
        "albums":  [dict(r) for r in albums],
        "classified": classified,
        "total": total,
    }


def music_era_profile():
    """Play-weighted mean, mode, and median release year plus decade distribution."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT ar.release_year, COUNT(*) AS plays
        FROM scrobbles s
        JOIN album_releases ar ON s.artist = ar.artist AND s.album = ar.album
        WHERE ar.release_year IS NOT NULL
          AND ar.release_year BETWEEN 1900 AND 2030
        GROUP BY ar.release_year
        ORDER BY ar.release_year
    """).fetchall()
    conn.close()

    if not rows:
        return None

    years  = [r["release_year"] for r in rows]
    plays  = [r["plays"]        for r in rows]
    total  = sum(plays)

    # weighted mean
    mean = sum(y * p for y, p in zip(years, plays)) / total

    # mode: year with the most plays
    mode = years[plays.index(max(plays))]

    # weighted median
    cumulative, median = 0, years[0]
    for y, p in zip(years, plays):
        cumulative += p
        if cumulative >= total / 2:
            median = y
            break

    # decade breakdown
    decade_map = {}
    for y, p in zip(years, plays):
        d = (y // 10) * 10
        decade_map[d] = decade_map.get(d, 0) + p

    return {
        "mean":   round(mean, 1),
        "mode":   mode,
        "median": median,
        "total_classified": total,
        "decade_distribution": [
            {"decade": k, "plays": v} for k, v in sorted(decade_map.items())
        ],
    }


def _ts_filter(ts_from, ts_to):
    clauses, params = [], []
    if ts_from:
        clauses.append("ts >= ?"); params.append(ts_from)
    if ts_to:
        clauses.append("ts <= ?"); params.append(ts_to)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
