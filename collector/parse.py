"""Turn raw ESPN responses into small, flat records we store in data/."""
import re

# season.type in ESPN: 1 preseason, 2 regular season, 3 postseason, 5 play-in
KEPT_SEASON_TYPES = {2, 3, 5}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _athlete_id(athlete):
    if athlete.get("id"):
        return str(athlete["id"])
    for link in athlete.get("links", []):
        m = re.search(r"/id/(\d+)", link.get("href", ""))
        if m:
            return m.group(1)
    return None


def parse_teams(raw):
    out = []
    for item in raw["sports"][0]["leagues"][0]["teams"]:
        t = item["team"]
        out.append({
            "id": t["id"],
            "abbr": t["abbreviation"],
            "name": t["displayName"],
            "short_name": t["shortDisplayName"],
            "location": t["location"],
            "color": t.get("color"),
            "logo": (t.get("logos") or [{}])[0].get("href"),
        })
    return sorted(out, key=lambda t: t["abbr"])


def parse_scoreboard(raw, team_ids):
    """Games from one scoreboard day. Skips preseason and All-Star games."""
    games = []
    for ev in raw.get("events", []):
        season = ev.get("season", {})
        if season.get("type") not in KEPT_SEASON_TYPES:
            continue
        comp = ev["competitions"][0]
        sides = {c["homeAway"]: c for c in comp["competitors"]}
        if {sides["home"]["team"]["id"], sides["away"]["team"]["id"]} - team_ids:
            continue
        status = comp["status"]["type"]
        game = {
            "id": ev["id"],
            "date": ev["date"],
            "season": season["year"],
            "season_type": season["type"],
            "state": status["state"],  # pre / in / post
            "completed": status["completed"],
            "status": status["name"],
            "neutral": comp.get("neutralSite", False),
            "venue": comp.get("venue", {}).get("fullName"),
        }
        for side in ("home", "away"):
            c = sides[side]
            game[side] = {
                "id": c["team"]["id"],
                "abbr": c["team"]["abbreviation"],
                "score": _int(c.get("score")) if status["state"] != "pre" else None,
            }
        odds = (comp.get("odds") or [None])[0]
        if odds:
            game["odds"] = {
                "provider": odds.get("provider", {}).get("name"),
                "details": odds.get("details"),
                "spread": odds.get("spread"),
                "over_under": odds.get("overUnder"),
            }
        games.append(game)
    return games


TEAM_STAT_FIELDS = {
    "fieldGoalsMade-fieldGoalsAttempted": ("fgm", "fga"),
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("fg3m", "fg3a"),
    "freeThrowsMade-freeThrowsAttempted": ("ftm", "fta"),
    "offensiveRebounds": "oreb",
    "defensiveRebounds": "dreb",
    "totalRebounds": "reb",
    "assists": "ast",
    "steals": "stl",
    "blocks": "blk",
    "totalTurnovers": "tov",
    "fouls": "pf",
    "pointsInPaint": "paint_pts",
    "fastBreakPoints": "fastbreak_pts",
}
TEAM_COLUMNS = ["game_id", "date", "season", "season_type", "team_id", "opp_id", "home",
                "pts", "opp_pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb",
                "reb", "ast", "stl", "blk", "tov", "pf", "paint_pts", "fastbreak_pts"]

PLAYER_KEYS = {
    "minutes": "min",
    "points": "pts",
    "fieldGoalsMade-fieldGoalsAttempted": ("fgm", "fga"),
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("fg3m", "fg3a"),
    "freeThrowsMade-freeThrowsAttempted": ("ftm", "fta"),
    "rebounds": "reb",
    "offensiveRebounds": "oreb",
    "defensiveRebounds": "dreb",
    "assists": "ast",
    "steals": "stl",
    "blocks": "blk",
    "turnovers": "tov",
    "fouls": "pf",
    "plusMinus": "plus_minus",
}
PLAYER_COLUMNS = ["game_id", "date", "season", "team_id", "athlete_id", "name", "position",
                  "starter", "dnp", "min", "pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
                  "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf", "plus_minus"]


def _assign(row, field, value):
    if isinstance(field, tuple):
        made, att = (value or "").split("-") if "-" in (value or "") else (None, None)
        row[field[0]], row[field[1]] = _int(made), _int(att)
    else:
        row[field] = _int(str(value).lstrip("+")) if value not in (None, "") else None


def parse_boxscore(raw, game):
    """Team and player box-score rows for one completed game."""
    base = {"game_id": game["id"], "date": game["date"][:10], "season": game["season"]}
    score = {game["home"]["id"]: game["home"]["score"], game["away"]["id"]: game["away"]["score"]}
    team_rows, player_rows = [], []
    box = raw.get("boxscore", {})
    for t in box.get("teams", []):
        tid = t["team"]["id"]
        opp = game["away"]["id"] if tid == game["home"]["id"] else game["home"]["id"]
        row = dict(base, season_type=game["season_type"], team_id=tid, opp_id=opp,
                   home=int(tid == game["home"]["id"]), pts=score.get(tid), opp_pts=score.get(opp))
        stats = {s["name"]: s.get("displayValue") for s in t.get("statistics", [])}
        for name, field in TEAM_STAT_FIELDS.items():
            _assign(row, field, stats.get(name))
        team_rows.append(row)
    for p in box.get("players", []):
        tid = p["team"]["id"]
        for block in p.get("statistics", []):
            keys = block.get("keys", [])
            for a in block.get("athletes", []):
                ath = a.get("athlete") or {}
                if not ath.get("id"):
                    continue
                row = dict(base, team_id=tid, athlete_id=ath["id"], name=ath["displayName"],
                           position=(ath.get("position") or {}).get("abbreviation"),
                           starter=int(bool(a.get("starter"))), dnp=int(bool(a.get("didNotPlay"))))
                for key, value in zip(keys, a.get("stats", [])):
                    if key in PLAYER_KEYS:
                        _assign(row, PLAYER_KEYS[key], value)
                player_rows.append(row)
    return team_rows, player_rows


def parse_injuries(raw):
    out = []
    for team in raw.get("injuries", []):
        for inj in team.get("injuries", []):
            ath = inj.get("athlete", {})
            details = inj.get("details") or {}
            out.append({
                "team_id": str(team["id"]),
                "team": team.get("displayName"),
                "athlete_id": _athlete_id(ath),
                "name": ath.get("displayName"),
                "position": (ath.get("position") or {}).get("abbreviation"),
                "status": inj.get("status"),
                "injury": " ".join(x for x in (details.get("side"), details.get("type"),
                                               details.get("detail")) if x) or None,
                "return_date": details.get("returnDate"),
                "updated": inj.get("date"),
                "comment": inj.get("shortComment"),
            })
    return out


def parse_standings(raw):
    out = []
    for conf in raw.get("children", []):
        for e in conf["standings"]["entries"]:
            stats = {s.get("type") or s.get("name"): s for s in e["stats"]}

            def val(key):
                s = stats.get(key)
                return s.get("displayValue") if s else None

            out.append({
                "team_id": e["team"]["id"],
                "abbr": e["team"]["abbreviation"],
                "conference": conf["name"],
                "seed": _int(stats.get("playoffseed", {}).get("value")),
                "wins": _int(stats.get("wins", {}).get("value")),
                "losses": _int(stats.get("losses", {}).get("value")),
                "win_pct": stats.get("winpercent", {}).get("value"),
                "games_behind": val("gamesbehind"),
                "home": val("home"),
                "road": val("road"),
                "last10": val("lasttengames"),
                "streak": val("streak"),
                "ppg": stats.get("avgpointsfor", {}).get("value"),
                "opp_ppg": stats.get("avgpointsagainst", {}).get("value"),
            })
    return sorted(out, key=lambda r: (r["conference"], r["seed"] or 99))


def parse_roster(raw, team_id):
    out = []
    for a in raw.get("athletes", []):
        out.append({
            "team_id": str(team_id),
            "athlete_id": a["id"],
            "name": a["displayName"],
            "jersey": a.get("jersey"),
            "position": (a.get("position") or {}).get("abbreviation"),
            "age": a.get("age"),
            "height": a.get("displayHeight"),
            "weight": a.get("displayWeight"),
            "experience": (a.get("experience") or {}).get("years"),
            "college": (a.get("college") or {}).get("name"),
            "headshot": (a.get("headshot") or {}).get("href"),
        })
    return out
