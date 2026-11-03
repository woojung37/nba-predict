"""Collect KBL and V-League games from API-Sports.

  python -m korea.collect backfill   # free-plan seasons (2023-24, 2024-25), ~6 requests
  python -m korea.collect daily      # yesterday/today/tomorrow, then predict (6 requests)
"""
import datetime as dt
import sys

from collector.store import DATA, read_json, write_json

from . import api
from .leagues import CURRENT_SEASON, FREE_HISTORY, ID_ALIAS, LEAGUES

KR = DATA / "kr"
MIN_GAP = dt.timedelta(minutes=50)  # skip API calls if the last daily fetch was this recent


def season_of(date, sport):
    """Starting year of the Korean season a game belongs to (seasons run Oct-May)."""
    d = dt.date.fromisoformat(date[:10])
    return d.year if d.month >= 8 else d.year - 1


STATUS_DONE = {"FT", "AOT", "AW"}


def normalize(raw, code):
    sport = LEAGUES[code]["sport"]
    st = raw["status"]["short"]
    g = {
        "id": str(raw["id"]),
        "date": raw["date"],
        "season": season_of(raw["date"], sport),
        "status": st,
        "completed": st in STATUS_DONE,
        "home": {"id": raw["teams"]["home"]["id"], "name": raw["teams"]["home"]["name"]},
        "away": {"id": raw["teams"]["away"]["id"], "name": raw["teams"]["away"]["name"]},
    }
    alias = ID_ALIAS.get(code, {})
    for side in ("home", "away"):
        g[side]["id"] = alias.get(g[side]["id"], g[side]["id"])
    if sport == "basketball":
        s = raw["scores"]
        g["home"]["score"], g["away"]["score"] = s["home"]["total"], s["away"]["total"]
        g["overtime"] = s["home"].get("over_time") is not None
    else:
        g["home"]["score"], g["away"]["score"] = raw["scores"]["home"], raw["scores"]["away"]
        sets = []
        for k in ("first", "second", "third", "fourth", "fifth"):
            p = (raw.get("periods") or {}).get(k) or {}
            if p.get("home") is not None and p.get("away") is not None:
                sets.append([p["home"], p["away"]])
        g["sets"] = sets
    if g["completed"] and (g["home"]["score"] is None or g["away"]["score"] is None):
        g["completed"] = False
    return g


def games_path(code):
    return KR / code / "games.json"


def merge(code, new_games):
    path = games_path(code)
    games = {g["id"]: g for g in read_json(path, [])}
    alias = ID_ALIAS.get(code, {})
    for g in games.values():
        for side in ("home", "away"):
            g[side]["id"] = alias.get(g[side]["id"], g[side]["id"])
    for g in new_games:
        games[g["id"]] = g
    out = sorted(games.values(), key=lambda g: (g["date"], g["id"]))
    write_json(path, out)
    return out


def backfill():
    for code, lg in LEAGUES.items():
        new = []
        for year in FREE_HISTORY:
            raw = api.get(lg["sport"], "games", league=lg["league_id"], season=lg["season_key"](year))
            new += [normalize(r, code) for r in raw]
        merge(code, new)
        print(code, len(new), "games")


def daily(force=False):
    meta = read_json(KR / "meta.json", {})
    now = dt.datetime.now(dt.timezone.utc)
    last = meta.get("fetched_utc")
    if not force and last and now - dt.datetime.fromisoformat(last) < MIN_GAP:
        print("fetched recently, skipping API calls")
    else:
        by_league = {code: [] for code in LEAGUES}
        ids = {lg["league_id"]: code for code, lg in LEAGUES.items()}
        for sport in ("basketball", "volleyball"):
            for delta in (-1, 0, 1):
                day = (now + dt.timedelta(days=delta)).date().isoformat()
                for r in api.get(sport, "games", date=day):
                    code = ids.get(r["league"]["id"])
                    if code and LEAGUES[code]["sport"] == sport:
                        by_league[code].append(normalize(r, code))
        for code, new in by_league.items():
            merge(code, new)
        meta["fetched_utc"] = now.isoformat(timespec="seconds")
    meta["updated_utc"] = now.isoformat(timespec="seconds")
    meta["current_season"] = CURRENT_SEASON
    write_json(KR / "meta.json", meta)
    from .predict import write_all
    write_all()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cmd == "backfill":
        backfill()
    elif cmd == "daily":
        daily(force="--force" in sys.argv)
    elif cmd == "predict":
        from .predict import write_all
        write_all()
    else:
        sys.exit(__doc__)
