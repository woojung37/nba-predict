"""API-Sports client (api-basketball / api-volleyball).

Free plan: 100 requests per day per sport, seasons up to 2024 only, and the
`date=` query only for yesterday, today and tomorrow. Every call is counted in
data/kr/meta.json so runs can stay under the limit.
"""
import json
import os
import time
import urllib.request

HOSTS = {"basketball": "v1.basketball.api-sports.io", "volleyball": "v1.volleyball.api-sports.io"}


class ApiError(RuntimeError):
    pass


def get(sport, path, **params):
    key = os.environ.get("API_SPORTS_KEY")
    if not key:
        raise ApiError("API_SPORTS_KEY is not set")
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://{HOSTS[sport]}/{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": key, "User-Agent": "nba-predict"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.load(r)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    errors = body.get("errors")
    if errors:
        raise ApiError(f"{sport} {path} {params}: {errors}")
    return body["response"]
