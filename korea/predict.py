"""Predict upcoming KBL / V-League games, log pre-game predictions, track record."""
import datetime as dt
from collections import defaultdict
from pathlib import Path

from collector.store import read_json, write_json
from model.engine import win_probability

from . import volley
from .collect import KR
from .leagues import CURRENT_SEASON, LEAGUES, TEAM_KO
from .train import kbl_replay

PARAMS_PATH = Path(__file__).resolve().parent / "params.json"
RANGE_Z = 1.2816
LOW_DATA = 5  # fewer current-season games than this -> low-confidence label


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def started(g):
    return dt.datetime.fromisoformat(g["date"]) <= now_utc()


def team(t):
    return {"id": t["id"], "name": t["name"], "ko": TEAM_KO.get(t["name"], t["name"])}


def standings(games):
    table = defaultdict(lambda: {"w": 0, "l": 0, "pf": 0, "pa": 0})
    names = {}
    for g in games:
        if g["season"] != CURRENT_SEASON or not g["completed"]:
            continue
        for side, opp in (("home", "away"), ("away", "home")):
            t = table[g[side]["id"]]
            names[g[side]["id"]] = g[side]
            won = g[side]["score"] > g[opp]["score"]
            t["w" if won else "l"] += 1
            if g.get("sets"):
                t["pf"] += sum(s[0 if side == "home" else 1] for s in g["sets"])
                t["pa"] += sum(s[1 if side == "home" else 0] for s in g["sets"])
            else:
                t["pf"] += g[side]["score"]
                t["pa"] += g[opp]["score"]
    return table, names


def kbl_prediction(r, params, g):
    h, a = g["home"]["id"], g["away"]["id"]
    d = (dt.datetime.fromisoformat(g["date"]) + dt.timedelta(hours=9)).date()
    b2b = (r.b2b(h, d), r.b2b(a, d))
    hp, ap = r.predict(h, a, False, b2b)
    margin, total = hp - ap, hp + ap
    sigma, ts = params["sigma"], params["total_sigma"]
    prob = win_probability(margin, sigma)
    return {
        "home_points": round(hp, 1), "away_points": round(ap, 1), "home_margin": round(margin, 1),
        "home_win_prob": round(prob, 3), "total": round(total, 1),
        "margin_range80": [round(margin - RANGE_Z * sigma, 1), round(margin + RANGE_Z * sigma, 1)],
        "total_range80": [round(total - RANGE_Z * ts, 1), round(total + RANGE_Z * ts, 1)],
        "sigma": sigma, "total_sigma": ts,
        "factors": {"team_strength": round((r.O[h] - r.D[h]) - (r.O[a] - r.D[a]), 1),
                    "home_court": params["hca"], "rest": round(-params["b2b"] * (b2b[0] - b2b[1]), 1)},
        "back_to_back": {"home": bool(b2b[0]), "away": bool(b2b[1])},
    }


def volley_prediction(r, params, g):
    d = r.predict(g["home"]["id"], g["away"]["id"])
    total = d["expected_total"] + params.get("total_bias", 0)
    ts = params["total_sigma"]
    s = d["scores"]
    return {
        "home_win_prob": round(d["home_win_prob"], 3),
        "scores": {k: round(v, 3) for k, v in s.items()},
        "set_win_prob": round(d["set_win_prob"], 3),
        "expected_sets": round(d["expected_sets"], 2),
        "total": round(total, 1),
        "total_range80": [round(total - RANGE_Z * ts, 1), round(total + RANGE_Z * ts, 1)],
        "total_sigma": ts,
        # set handicap: home -1.5 = home wins 3-0/3-1; home +1.5 = home takes at least two sets
        "home_minus_1_5": round(s["3-0"] + s["3-1"], 3),
        "away_minus_1_5": round(s["0-3"] + s["1-3"], 3),
        "full_five_sets": round(s["3-2"] + s["2-3"], 3),
        "edge": round(r.edge(g["home"]["id"], g["away"]["id"]), 3),
    }


def track_record(log, sport):
    done = [e for e in log.values() if "result" in e]
    if not done:
        return {"games": 0}
    hw = lambda e: e["result"]["home_score"] > e["result"]["away_score"]
    correct = sum((e["prediction"]["home_win_prob"] > 0.5) == hw(e) for e in done)
    out = {"games": len(done), "correct": correct, "win_accuracy": round(correct / len(done), 4)}
    if sport == "basketball":
        out["margin_mae"] = round(sum(abs(e["prediction"]["home_margin"] - e["result"]["home_margin"])
                                      for e in done) / len(done), 2)
    else:
        sc = lambda e: f'{e["result"]["home_score"]}-{e["result"]["away_score"]}'
        out["set_score_exact"] = round(sum(max(e["prediction"]["scores"], key=e["prediction"]["scores"].get) == sc(e)
                                           for e in done) / len(done), 4)
    out["total_mae"] = round(sum(abs(e["prediction"]["total"] - e["result"]["total"]) for e in done) / len(done), 2)
    return out


def write_league(code, params):
    lg = LEAGUES[code]
    sport = lg["sport"]
    games = read_json(KR / code / "games.json", [])
    done = [g for g in games if g["completed"]]
    if sport == "basketball":
        r = kbl_replay(done, params)
        if r.season is not None and r.season < CURRENT_SEASON:  # carry ratings into the new season
            gap = CURRENT_SEASON - r.season
            for t in list(r.O):
                r.O[t] *= params["regress"] ** gap
                r.D[t] *= params["regress"] ** gap
            r.season = CURRENT_SEASON
        rating = lambda t: round(r.O[t] - r.D[t], 1)
        ids = set(r.O)
        predict = lambda g: kbl_prediction(r, params, g)
    else:
        r = volley.replay(done, params)
        r.new_season(CURRENT_SEASON)
        rating = lambda t: round(r.a[t], 3)
        ids = set(r.a)
        predict = lambda g: volley_prediction(r, params, g)

    table, names = standings(games)
    played = {t: v["w"] + v["l"] for t, v in table.items()}
    log_path = KR / code / "predictions_log.json"
    log = read_json(log_path, {})
    stamp = now_utc().isoformat(timespec="seconds")
    upcoming = []
    for g in games:
        if g["completed"] or g["season"] != CURRENT_SEASON or g["status"] in ("CANC", "PST", "ABD"):
            continue
        entry = {"id": g["id"], "date": g["date"], "status": g["status"],
                 "home": team(g["home"]), "away": team(g["away"])}
        if not started(g):
            entry["prediction"] = predict(g)
            entry["data_games"] = {"home": played.get(g["home"]["id"], 0), "away": played.get(g["away"]["id"], 0)}
            entry["low_confidence"] = min(entry["data_games"].values()) < LOW_DATA
            log[g["id"]] = {"date": g["date"], "home": entry["home"]["ko"], "away": entry["away"]["ko"],
                            "predicted_at": stamp, "prediction": entry["prediction"]}
        elif g["id"] in log:
            entry["prediction"] = log[g["id"]]["prediction"]
        upcoming.append(entry)
    by_id = {g["id"]: g for g in games}
    for gid, e in log.items():
        g = by_id.get(gid)
        if g and g["completed"] and "result" not in e:
            total = sum(sum(s) for s in g["sets"]) if g.get("sets") else g["home"]["score"] + g["away"]["score"]
            e["result"] = {"home_score": g["home"]["score"], "away_score": g["away"]["score"],
                           "home_margin": g["home"]["score"] - g["away"]["score"], "total": total}
            if g.get("sets"):
                e["result"]["sets"] = g["sets"]
    recent = [{"id": g["id"], "date": g["date"], "home": team(g["home"]), "away": team(g["away"]),
               "home_score": g["home"]["score"], "away_score": g["away"]["score"], "sets": g.get("sets"),
               "pre_game_prediction": (log.get(g["id"]) or {}).get("prediction")}
              for g in done if g["season"] == CURRENT_SEASON][-30:][::-1]
    latest = {}
    for g in games:  # most recent name for every team seen
        for side in ("home", "away"):
            latest[g[side]["id"]] = g[side]
    last_season = max(g["season"] for g in games)
    active = {g[s]["id"] for g in games for s in ("home", "away") if g["season"] >= min(last_season, CURRENT_SEASON) - 2}
    teams = []
    for t in active:
        row = table.get(t, {"w": 0, "l": 0, "pf": 0, "pa": 0})
        teams.append({**team(latest[t]), "wins": row["w"], "losses": row["l"], "points_for": row["pf"],
                      "points_against": row["pa"], "rating": rating(t)})
    teams.sort(key=lambda x: (-(x["wins"] / max(1, x["wins"] + x["losses"])), -x["rating"]))
    write_json(KR / code / "upcoming.json", sorted(upcoming, key=lambda e: e["date"]))
    write_json(KR / code / "recent.json", recent)
    write_json(KR / code / "teams.json", teams)
    write_json(log_path, dict(sorted(log.items(), key=lambda kv: kv[1]["date"])))
    write_json(KR / code / "track_record.json", track_record(log, sport))


def write_all():
    params = read_json(PARAMS_PATH, {})
    for code in LEAGUES:
        if code in params:
            write_league(code, params[code])
