# Last.fm Stats

A local web dashboard that downloads your complete Last.fm scrobble history and generates custom reports — things the official Last.fm site either doesn't offer or locks behind a paywall.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Flask](https://img.shields.io/badge/flask-3.x-green) ![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Sync** your full scrobble history into a local SQLite database
- **Timeline** — scrobbles per month or per year, with year filter
- **Top Artists / Albums / Tracks** — filterable by date range
- **Depth ranking** — artists and albums ranked by geometric mean of plays per unique track (rewards breadth, not just total plays)
- **Smart album score** — combines depth with release-year age normalization
- **Trending artists** — linear regression over weekly / monthly / yearly windows
- **Listening patterns** — hour-of-day and day-of-week heatmaps
- **Wrapped** — year-in-review: top artists, albums, tracks, and newly discovered artists
- **Music Era Profile** — your favorite decade and peak year by plays-per-album density, with a full decade distribution chart
- **Decade Browser** — top artists, albums, and tracks broken down by release decade
- **Artist profiles** — click any artist name for a full modal: first/last listen, top tracks, album stats, monthly activity chart
- **Artist name correction** — uses Last.fm's `artist.getCorrection` API to normalize inconsistent spellings in your history
- **Release year fetching** — bulk-fetches album release years from Last.fm and MusicBrainz, powering the era features

## Requirements

- Python 3.9+
- A [Last.fm API key](https://www.last.fm/api/account/create) (free)

## Setup

```bash
git clone https://github.com/alexdomini/lastfm-stats.git
cd lastfm-stats
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your API key and username
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Configuration

Copy `.env.example` to `.env` and set:

```
LASTFM_API_KEY=your_api_key_here
LASTFM_USER=your_lastfm_username
```

## Usage

1. Click **Sync** to download your scrobble history (first sync can take a few minutes for large libraries)
2. Explore the dashboard sections: Timeline, Top Lists, Patterns, Trending, Wrapped
3. Optionally click **Fetch Release Years** to enable the Music Era Profile and Decade Browser (fetches from Last.fm + MusicBrainz; only missing albums are queried on subsequent runs)
4. Optionally click **Correct Artist Names** to normalize artist name variations using Last.fm's correction API

## Tech stack

- **Backend**: Python, Flask, SQLite
- **Frontend**: Vanilla JS, Chart.js
- **Data source**: [Last.fm API](https://www.last.fm/api)

## Last.fm ToS compliance

This project is non-commercial and personal-use only. All data is stored locally on your machine. The UI includes proper attribution to Last.fm as required by their [API Terms of Service](https://www.last.fm/api/tos).

---

*Powered by Last.fm & AudioScrobbler*
