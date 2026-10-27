"""Thin client for ESPN's public NBA JSON endpoints (no API key needed)."""
import json
import time
import urllib.error
import urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
HEADERS = {"User-Agent": "Mozilla/5.0 (nba-predict data collector)"}


def get_json(url, retries=4, pause=0.15):
    """GET a URL and decode JSON, retrying transient failures with backoff."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            time.sleep(pause)
            return data
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            status = getattr(exc, "code", None)
            if status == 404 or attempt == retries:
                raise
            time.sleep(2 ** attempt)


def scoreboard(day):
    """Games on one US-Eastern date (datetime.date)."""
    return get_json(f"{SITE}/scoreboard?dates={day:%Y%m%d}&limit=100")


def summary(event_id):
    return get_json(f"{SITE}/summary?event={event_id}")


def teams():
    return get_json(f"{SITE}/teams")


def roster(team_id):
    return get_json(f"{SITE}/teams/{team_id}/roster")


def injuries():
    return get_json(f"{SITE}/injuries")


def standings():
    return get_json(STANDINGS)
