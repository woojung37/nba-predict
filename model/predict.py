"""Predict upcoming games and keep a log of pre-game predictions.

Called by the collector after each data refresh (see collector/collect.py).
"""
import datetime as dt
from collections import defaultdict
from pathlib import Path

from collector.store import read_json, write_json

from .engine import INJURY_WEIGHT, load_history, replay, us_day, win_probability

PARAMS_PATH = Path(__file__).resolve().parent / "params.json"
RANGE_Z = 1.2816  # 80% of games land inside the predicted margin range


def predict_game(g, ratings, players, injuries, params):
    h, a = g["home"]["id"], g["away"]["id"]
    day = us_day(g["date"])
    b2b = (ratings.b2b(h, day), ratings.b2b(a, day))
    out_players = {}
    missing = []
    for team in (h, a):
        hurt = {i["athlete_id"]: i for i in injuries.get(team, [])}
        total = 0.0
        listed = []
        for athlete, value in players.rotation(team).items():
            inj = hurt.get(athlete)
            weight = INJURY_WEIGHT.get(inj["status"], 0.0) if inj else 0.0
            if weight and value:
                total += weight * value
                listed.append({"athlete_id": athlete, "name": players.names.get(athlete),
                               "status": inj["status"],
                               "impact": round(-params["injury"] * weight * value, 1)})
        missing.append(total)
        out_players[team] = sorted(listed, key=lambda x: x["impact"])
    home_pts, away_pts = ratings.predict(h, a, g["neutral"], b2b, tuple(missing))
    margin = home_pts - away_pts
    sigma = params["sigma"]
    prob = win_probability(margin, sigma)
    hca = 0.0 if g["neutral"] else params["hca"]
    total = home_pts + away_pts
    total_sigma = params["total_sigma"]
    out = {
        "home_points": round(home_pts, 1),
        "away_points": round(away_pts, 1),
        "home_margin": round(margin, 1),
        "home_win_prob": round(prob, 3),
        "away_win_prob": round(1 - prob, 3),
        "margin_range80": [round(margin - RANGE_Z * sigma, 1), round(margin + RANGE_Z * sigma, 1)],
        "total": round(total, 1),
        "total_range80": [round(total - RANGE_Z * total_sigma, 1), round(total + RANGE_Z * total_sigma, 1)],
        "sigma": sigma,
        "total_sigma": total_sigma,
        # these add up to home_margin
        "factors": {
            "team_strength": round((ratings.O[h] - ratings.D[h]) - (ratings.O[a] - ratings.D[a]), 1),
            "home_court": round(hca, 1),
            "rest": round(-params["b2b"] * (b2b[0] - b2b[1]), 1),
            "injuries": round(-params["injury"] * (missing[0] - missing[1]), 1),
        },
        "back_to_back": {"home": bool(b2b[0]), "away": bool(b2b[1])},
        "injury_impact": {"home": out_players[h], "away": out_players[a]},
        "ratings": {side: {"offense": round(ratings.O[t], 1), "defense": round(ratings.D[t], 1)}
                    for side, t in (("home", h), ("away", a))},
    }
    odds = g.get("odds") or {}
    if odds.get("spread") is not None or odds.get("over_under") is not None:
        out["vs_line"] = line_probabilities(margin, total, odds.get("spread"), odds.get("over_under"),
                                            sigma, total_sigma)
        out["vs_line"]["provider"] = odds.get("provider")
    return out


def line_probabilities(margin, total, spread, over_under, sigma, total_sigma):
    """Chance the home team covers `spread` (home line, negative = favored) and the game goes over."""
    res = {"spread": spread, "over_under": over_under}
    if spread is not None:
        res["home_cover_prob"] = round(win_probability(margin + spread, sigma), 3)
    if over_under is not None:
        res["over_prob"] = round(win_probability(total - over_under, total_sigma), 3)
    return res


def track_record(log):
    done = [e for e in log.values() if "result" in e]
    if not done:
        return {"games": 0}
    correct = sum((e["prediction"]["home_margin"] > 0) == (e["result"]["home_margin"] > 0) for e in done)
    mae = sum(abs(e["prediction"]["home_margin"] - e["result"]["home_margin"]) for e in done) / len(done)
    inside = sum(e["prediction"]["margin_range80"][0] <= e["result"]["home_margin"]
                 <= e["prediction"]["margin_range80"][1] for e in done)
    out = {"games": len(done), "correct": correct, "win_accuracy": round(correct / len(done), 4),
           "margin_mae": round(mae, 2), "range80_coverage": round(inside / len(done), 4)}
    totals = [e for e in done if "total" in e["prediction"]]
    if totals:
        actual = lambda e: e["result"]["home_score"] + e["result"]["away_score"]
        out["total_mae"] = round(sum(abs(e["prediction"]["total"] - actual(e)) for e in totals) / len(totals), 2)
    out["handicap"] = line_record(done, "home_cover_prob", "spread",
                                  lambda e, line: e["result"]["home_margin"] + line)
    out["over_under"] = line_record(done, "over_prob", "over_under",
                                    lambda e, line: e["result"]["home_score"] + e["result"]["away_score"] - line)
    return out


def line_record(done, prob_key, line_key, outcome):
    """Hit rate of picking the side the model gives over 50%, pushes excluded."""
    stats = {"all": [0, 0], "confident": [0, 0]}  # [hits, decided games]
    for e in done:
        line = e.get("line") or {}
        if line.get(prob_key) is None or line.get(line_key) is None:
            continue
        diff = outcome(e, line[line_key])
        if diff == 0:
            continue
        prob = line[prob_key]
        hit = (prob > 0.5) == (diff > 0)
        buckets = ["all"] + (["confident"] if abs(prob - 0.5) >= 0.1 else [])
        for b in buckets:
            stats[b][0] += hit
            stats[b][1] += 1
    return {b: {"hits": h, "games": n, "hit_rate": round(h / n, 4) if n else None}
            for b, (h, n) in stats.items()}


def write_predictions(data, season):
    params = read_json(PARAMS_PATH)
    if not params:
        return
    ratings, players = replay(load_history(), params)
    injuries = defaultdict(list)
    for inj in read_json(data / "current" / "injuries.json", []):
        injuries[inj["team_id"]].append(inj)

    upcoming = read_json(data / "derived" / "upcoming.json", [])
    games = {g["id"]: g for g in read_json(data / "seasons" / str(season) / "games.json", [])}
    log_path = data / "model" / "predictions_log.json"
    log = read_json(log_path, {})
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for entry in upcoming:
        g = games.get(entry["id"])
        if g and g["state"] != "pre" and g["id"] in log:
            entry["pre_game_prediction"] = log[g["id"]]["prediction"]
        if not g or g["state"] != "pre":
            continue
        entry["prediction"] = predict_game(g, ratings, players, injuries, params)
        if dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00")) <= dt.datetime.now(dt.timezone.utc):
            continue  # ESPN can lag at tip-off; only log predictions made before the start
        log[g["id"]] = {"date": g["date"], "home": g["home"]["abbr"], "away": g["away"]["abbr"],
                        "predicted_at": now, "prediction": {k: entry["prediction"][k] for k in (
                            "home_points", "away_points", "home_margin", "home_win_prob",
                            "margin_range80", "total")}}
        if "vs_line" in entry["prediction"]:
            log[g["id"]]["line"] = entry["prediction"]["vs_line"]
    # attach final scores to logged predictions
    for gid, e in log.items():
        g = games.get(gid)
        if g and g["completed"] and "result" not in e:
            e["result"] = {"home_score": g["home"]["score"], "away_score": g["away"]["score"],
                           "home_margin": g["home"]["score"] - g["away"]["score"]}
    write_json(data / "derived" / "upcoming.json", upcoming)
    write_json(log_path, dict(sorted(log.items(), key=lambda kv: kv[1]["date"])))
    write_json(data / "model" / "track_record.json", track_record(log))
    write_json(data / "derived" / "power_ratings.json", sorted(
        [{"team_id": t, "offense": round(ratings.O[t], 1), "defense": round(ratings.D[t], 1),
          "net": round(ratings.O[t] - ratings.D[t], 1)} for t in ratings.O],
        key=lambda r: -r["net"]))
