"""Build the files the website reads (data/derived/) from stored raw data."""
import datetime as dt
from collections import defaultdict

from .store import read_csv, read_json, write_json

UPCOMING_HOURS = 60  # covers "today and tomorrow" in Korea from any run time


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r(x, n=1):
    return round(x, n) if x is not None else None


def possessions(row):
    return row["fga"] - row["oreb"] + row["tov"] + 0.44 * row["fta"]


def team_stats(games, team_rows):
    """Season record, scoring, last-10 form and per-100 efficiency per team."""
    out = {}
    by_team = defaultdict(list)
    for g in games:
        if not g["completed"] or g["home"]["score"] is None:
            continue
        for side, other in (("home", "away"), ("away", "home")):
            by_team[g[side]["id"]].append({
                "date": g["date"], "home": side == "home",
                "margin": g[side]["score"] - g[other]["score"],
                "pts": g[side]["score"], "opp_pts": g[other]["score"],
            })
    box = defaultdict(list)
    for r in team_rows:
        box[r["team_id"]].append({k: _num(v) for k, v in r.items()})
    opp_box = {(r["game_id"], r["opp_id"]): r for r in team_rows}

    for tid, rows in by_team.items():
        rows.sort(key=lambda r: r["date"])
        last10 = rows[-10:]
        rec = lambda rs: [sum(r["margin"] > 0 for r in rs), sum(r["margin"] < 0 for r in rs)]
        avg = lambda rs, k: sum(r[k] for r in rs) / len(rs) if rs else None
        stats = {
            "gp": len(rows),
            "record": rec(rows),
            "home_record": rec([r for r in rows if r["home"]]),
            "away_record": rec([r for r in rows if not r["home"]]),
            "ppg": _r(avg(rows, "pts")),
            "opp_ppg": _r(avg(rows, "opp_pts")),
            "avg_margin": _r(avg(rows, "margin")),
            "last10_record": rec(last10),
            "last10_margin": _r(avg(last10, "margin")),
            "last_game": rows[-1]["date"],
        }
        own = [r for r in box.get(tid, []) if None not in (r["fga"], r["oreb"], r["tov"], r["fta"])]
        if own:
            poss = pts = opp_pts = 0.0
            for r in own:
                opp = opp_box.get((str(int(r["game_id"])), tid))
                if not opp:
                    continue
                o = {k: _num(v) for k, v in opp.items()}
                p = (possessions(r) + possessions(o)) / 2
                poss, pts, opp_pts = poss + p, pts + r["pts"], opp_pts + o["pts"]
            if poss:
                stats["pace"] = _r(poss / len(own))
                stats["ortg"] = _r(100 * pts / poss)
                stats["drtg"] = _r(100 * opp_pts / poss)
                stats["net_rtg"] = _r(stats["ortg"] - stats["drtg"])
        out[tid] = stats
    return out


def player_stats(player_rows):
    """Per-game averages for every player who appeared this season."""
    agg = {}
    sums = ["min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a",
            "ftm", "fta", "plus_minus"]
    for r in player_rows:
        if r["dnp"] == "1" or not r["min"]:
            continue
        p = agg.setdefault(r["athlete_id"], {"athlete_id": r["athlete_id"], "gp": 0, "gs": 0,
                                             **{k: 0.0 for k in sums}})
        p.update(name=r["name"], position=r["position"], team_id=r["team_id"], last_game=r["date"])
        p["gp"] += 1
        p["gs"] += int(r["starter"])
        for k in sums:
            p[k] += _num(r[k]) or 0
    out = []
    for p in agg.values():
        gp = p["gp"]
        row = {k: p[k] for k in ("athlete_id", "name", "position", "team_id", "gp", "gs", "last_game")}
        for k in ("min", "pts", "reb", "ast", "stl", "blk", "tov", "plus_minus"):
            row[k] = _r(p[k] / gp)
        for pct, (m, a) in {"fg_pct": ("fgm", "fga"), "fg3_pct": ("fg3m", "fg3a"),
                            "ft_pct": ("ftm", "fta")}.items():
            row[pct] = _r(100 * p[m] / p[a]) if p[a] else None
        out.append(row)
    return sorted(out, key=lambda r: -r["pts"])


def head_to_head(team_a, team_b, all_games, limit=10):
    meetings = [g for g in all_games if g["completed"] and g["home"]["score"] is not None
                and {g["home"]["id"], g["away"]["id"]} == {team_a, team_b}]
    meetings.sort(key=lambda g: g["date"], reverse=True)
    a_wins = 0
    margins = []
    listed = []
    for g in meetings:
        side = "home" if g["home"]["id"] == team_a else "away"
        other = "away" if side == "home" else "home"
        margin = g[side]["score"] - g[other]["score"]
        a_wins += margin > 0
        margins.append(margin)
        listed.append({"id": g["id"], "date": g["date"], "season": g["season"],
                       "home": g["home"]["abbr"], "away": g["away"]["abbr"],
                       "home_score": g["home"]["score"], "away_score": g["away"]["score"]})
    return {
        "games": len(meetings),
        "wins": a_wins,
        "losses": len(meetings) - a_wins,
        "avg_margin": _r(sum(margins) / len(margins)) if margins else None,
        "recent": listed[:limit],
    }


def rest_days(team_id, game_date, games):
    before = [g["date"] for g in games if g["date"] < game_date
              and team_id in (g["home"]["id"], g["away"]["id"])]
    if not before:
        return None
    last = dt.datetime.fromisoformat(max(before).replace("Z", "+00:00"))
    now = dt.datetime.fromisoformat(game_date.replace("Z", "+00:00"))
    # ESPN dates are UTC; compare US calendar days (UTC-5 is close enough here)
    return ((now - dt.timedelta(hours=5)).date() - (last - dt.timedelta(hours=5)).date()).days - 1


def build_all(data, season):
    games = read_json(data / "seasons" / str(season) / "games.json", [])
    history = []
    for path in sorted((data / "seasons").glob("*/games.json")):
        history.extend(read_json(path, []))
    teams = {t["id"]: t for t in read_json(data / "teams.json", [])}
    team_rows = read_csv(data / "seasons" / str(season) / "team_games.csv")
    players = player_stats(read_csv(data / "seasons" / str(season) / "player_games.csv"))
    tstats = team_stats(games, team_rows)
    standings = {s["team_id"]: s for s in read_json(data / "current" / "standings.json", [])}
    injuries = defaultdict(list)
    for inj in read_json(data / "current" / "injuries.json", []):
        injuries[inj["team_id"]].append(inj)

    derived = data / "derived"
    write_json(derived / "team_stats.json", tstats)
    write_json(derived / "player_stats.json", players)

    now = dt.datetime.now(dt.timezone.utc)
    horizon = now + dt.timedelta(hours=UPCOMING_HOURS)
    upcoming = []
    for g in games:
        start = dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
        if g["completed"] or not (now - dt.timedelta(hours=4) <= start <= horizon):
            continue
        entry = {k: g[k] for k in ("id", "date", "season_type", "state", "neutral", "venue")}
        entry["date_kst"] = start.astimezone(dt.timezone(dt.timedelta(hours=9))).isoformat()
        if "odds" in g:
            entry["odds"] = g["odds"]
        for side in ("home", "away"):
            tid = g[side]["id"]
            injured = {i["athlete_id"]: i["status"] for i in injuries.get(tid, [])}
            top = [dict(p, injury_status=injured.get(p["athlete_id"]))
                   for p in players if p["team_id"] == tid][:5]
            entry[side] = {
                "id": tid,
                "abbr": g[side]["abbr"],
                "name": teams.get(tid, {}).get("name"),
                "standing": standings.get(tid),
                "stats": tstats.get(tid),
                "rest_days": rest_days(tid, g["date"], games),
                "injuries": injuries.get(tid, []),
                "top_players": top,
            }
        entry["head_to_head"] = head_to_head(g["home"]["id"], g["away"]["id"], history)
        upcoming.append(entry)
    write_json(derived / "upcoming.json", upcoming)
