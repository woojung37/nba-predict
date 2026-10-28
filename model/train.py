"""Tune the model on one season and test it on the next one it has not seen.

  python -m model.train            # tune on 2024-25, test on 2025-26
"""
import itertools
import json
import math
import statistics
from pathlib import Path

from collector.store import DATA, write_json

from .engine import load_history, replay, win_probability

PARAMS_PATH = Path(__file__).resolve().parent / "params.json"
TUNE_SEASON, TEST_SEASON = 2025, 2026
WARMUP_GAMES = 150
TOTAL_SIGMA = [None]  # set once tuned; used for total-points range coverage  # ratings start from zero in the first season

GRID = {
    "k": [0.03, 0.045, 0.06, 0.08],
    "hca": [1.5, 2.0, 2.5, 3.0],
    "b2b": [1.0, 2.0, 3.0, 4.0],
    "injury": [0.0, 0.1, 0.2, 0.3, 0.45],
    "regress": [0.5, 0.7],
}


def collect(games, params, season):
    rows = []

    def on_game(g, pred, actual, ctx):
        if g["season"] == season:
            rows.append((g, pred[0] - pred[1], actual[0] - actual[1], sum(pred), sum(actual), ctx))

    replay(games, params, on_game)
    return rows


def metrics(rows, sigma):
    n = len(rows)
    correct = sum((p > 0) == (a > 0) for _, p, a, *_ in rows)
    mae = sum(abs(p - a) for _, p, a, *_ in rows) / n
    brier = logloss = 0.0
    inside = 0
    for _, p, a, *_ in rows:
        prob = min(max(win_probability(p, sigma), 1e-6), 1 - 1e-6)
        won = a > 0
        brier += (prob - won) ** 2
        logloss -= math.log(prob if won else 1 - prob)
        inside += abs(a - p) <= 1.2816 * sigma
    totals = [(pt, at) for _, _, _, pt, at, _ in rows]
    total_sigma = TOTAL_SIGMA[0] or 1.0
    return {
        "games": n,
        "total_mae": round(sum(abs(pt - at) for pt, at in totals) / n, 2),
        "total_bias": round(sum(at - pt for pt, at in totals) / n, 2),
        "total_range80_coverage": round(sum(abs(at - pt) <= 1.2816 * total_sigma for pt, at in totals) / n, 4),
        "win_accuracy": round(correct / n, 4),
        "margin_mae": round(mae, 2),
        "brier": round(brier / n, 4),
        "log_loss": round(logloss / n, 4),
        "range80_coverage": round(inside / n, 4),
    }


def calibration(rows, sigma):
    buckets = {}
    for _, p, a, *_ in rows:
        prob = win_probability(p, sigma)
        fav_prob, fav_won = (prob, a > 0) if prob >= 0.5 else (1 - prob, a < 0)
        b = min(int(fav_prob * 10), 9) / 10
        n, w = buckets.get(b, (0, 0))
        buckets[b] = (n + 1, w + fav_won)
    return [{"bucket": f"{int(b*100)}-{int(b*100)+10}%", "games": n, "favorite_won": round(w / n, 3)}
            for b, (n, w) in sorted(buckets.items())]


def main():
    games = load_history([TUNE_SEASON, TEST_SEASON])
    best = None
    keys = list(GRID)
    for values in itertools.product(*GRID.values()):
        params = dict(zip(keys, values))
        rows = collect(games, params, TUNE_SEASON)[WARMUP_GAMES:]
        mse = sum((p - a) ** 2 for _, p, a, *_ in rows) / len(rows)
        if best is None or mse < best[0]:
            best = (mse, params, rows)
    _, params, tune_rows = best
    params["sigma"] = round(statistics.pstdev([a - p for _, p, a, *_ in tune_rows]), 2)
    total_resid = [a - p for *_, p, a, _ in [(r[0], r[3], r[4], r[5]) for r in tune_rows]]
    params["total_sigma"] = round(statistics.pstdev(total_resid), 2)
    TOTAL_SIGMA[0] = params["total_sigma"]
    write_json(PARAMS_PATH, params)

    test_rows = collect(games, params, TEST_SEASON)
    report = {
        "params": params,
        "tuned_on": "2024-25",
        "tested_on": "2025-26",
        "tune": metrics(tune_rows, params["sigma"]),
        "test": metrics(test_rows, params["sigma"]),
        "test_regular_season": metrics([r for r in test_rows if r[0]["season_type"] == 2], params["sigma"]),
        "test_playoffs": metrics([r for r in test_rows if r[0]["season_type"] in (3, 5)], params["sigma"]),
        "baseline_home_team_wins": round(sum(a > 0 for _, _, a, *_ in test_rows) / len(test_rows), 4),
        "calibration": calibration(test_rows, params["sigma"]),
        "test_games": [{
            "id": g["id"], "date": g["date"], "home": g["home"]["abbr"], "away": g["away"]["abbr"],
            "pred_home": round((pt + p) / 2, 1), "pred_away": round((pt - p) / 2, 1),
            "home_score": g["home"]["score"], "away_score": g["away"]["score"],
            "home_win_prob": round(win_probability(p, params["sigma"]), 3),
        } for g, p, a, pt, *_ in test_rows],
    }
    write_json(DATA / "model" / "backtest.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "test_games"}, indent=1))


if __name__ == "__main__":
    main()
