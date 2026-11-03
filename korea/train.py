"""Tune the Korean league models on 2023-24 and test them on 2024-25.

  python -m korea.train
"""
import itertools
import json
import math
import statistics
from pathlib import Path

from collector.store import read_json, write_json
from model.engine import Ratings, win_probability

from . import volley
from .collect import KR

PARAMS_PATH = Path(__file__).resolve().parent / "params.json"
TUNE, TEST = 2023, 2024
# Between-season carry-over can't be tuned: the tuning season is the first one we
# have, so it is fixed by judgement (half of last season's rating is kept).
REGRESS = 0.5
WARMUP = {"kbl": 60, "vmen": 25, "vwomen": 25}  # first-season games used only to seed ratings

KBL_GRID = {"k": [0.03, 0.05, 0.07, 0.1], "hca": [0.0, 1.0, 2.0, 3.0], "b2b": [0.0, 1.5, 3.0]}
VOLLEY_GRID = {"k": [0.1, 0.2, 0.3, 0.45], "hca": [0.0, 0.02, 0.04], "tau": [0.0, 0.15, 0.3, 0.45]}


def completed(code):
    return [g for g in read_json(KR / code / "games.json", []) if g["completed"]]


def day(g):
    import datetime as dt
    return (dt.datetime.fromisoformat(g["date"]) + dt.timedelta(hours=9)).date()


# ---------- KBL ----------
def kbl_replay(games, params, on_game=None):
    r = Ratings(dict(params, league_start=80.0, cap=25, injury=0.0))
    for g in games:
        if r.season is not None and g["season"] - r.season > 1:
            for t in list(r.O):  # skipped seasons (not on the free plan): regress once more each
                r.O[t] *= params["regress"] ** (g["season"] - r.season - 1)
                r.D[t] *= params["regress"] ** (g["season"] - r.season - 1)
        r.new_season(g["season"])
        h, a, d = g["home"]["id"], g["away"]["id"], day(g)
        b2b = (r.b2b(h, d), r.b2b(a, d))
        pred = r.predict(h, a, False, b2b)
        if g["completed"]:
            actual = (g["home"]["score"], g["away"]["score"])
            if on_game:
                on_game(g, pred, actual)
            r.update(h, a, pred, actual, d)
    return r


def kbl_rows(games, params, season):
    rows = []
    kbl_replay(games, params, lambda g, p, a: g["season"] == season and rows.append((g, p, a)))
    return rows


def kbl_metrics(rows, sigma, total_sigma):
    n = len(rows)
    m = [(p[0] - p[1], a[0] - a[1], sum(p), sum(a)) for _, p, a in rows]
    probs = [min(max(win_probability(pm, sigma), 1e-6), 1 - 1e-6) for pm, *_ in m]
    return {
        "games": n,
        "win_accuracy": round(sum((pm > 0) == (am > 0) for pm, am, *_ in m) / n, 4),
        "margin_mae": round(sum(abs(pm - am) for pm, am, *_ in m) / n, 2),
        "total_mae": round(sum(abs(pt - at) for *_, pt, at in m) / n, 2),
        "brier": round(sum((p - (am > 0)) ** 2 for p, (_, am, *_) in zip(probs, m)) / n, 4),
        "log_loss": round(-sum(math.log(p if am > 0 else 1 - p) for p, (_, am, *_) in zip(probs, m)) / n, 4),
        "range80_coverage": round(sum(abs(am - pm) <= 1.2816 * sigma for pm, am, *_ in m) / n, 4),
        "home_team_won": round(sum(am > 0 for _, am, *_ in m) / n, 4),
    }


def train_kbl():
    games = completed("kbl")
    best = None
    for values in itertools.product(*KBL_GRID.values()):
        params = dict(zip(KBL_GRID, values), regress=REGRESS)
        rows = kbl_rows(games, params, TUNE)[WARMUP["kbl"]:]
        mse = sum(((p[0] - p[1]) - (a[0] - a[1])) ** 2 for _, p, a in rows) / len(rows)
        if best is None or mse < best[0]:
            best = (mse, params, rows)
    _, params, rows = best
    params["sigma"] = round(statistics.pstdev([(a[0] - a[1]) - (p[0] - p[1]) for _, p, a in rows]), 2)
    params["total_sigma"] = round(statistics.pstdev([sum(a) - sum(p) for _, p, a in rows]), 2)
    test = kbl_rows(games, params, TEST)
    report = {"league": "kbl", "tuned_on": "2023-24", "tested_on": "2024-25", "params": params,
              "tune": kbl_metrics(rows, params["sigma"], params["total_sigma"]),
              "test": kbl_metrics(test, params["sigma"], params["total_sigma"])}
    return params, report


# ---------- V-League ----------
def volley_rows(games, params, season):
    rows = []
    volley.replay(games, params, lambda g, d: g["season"] == season and rows.append((g, d)))
    return rows


def outcome(g):
    return f'{g["home"]["score"]}-{g["away"]["score"]}'


def volley_metrics(rows):
    n = len(rows)
    win_ok = ll = sll = exact = hcap_ok = tot_err = 0.0
    for g, d in rows:
        hw = g["home"]["score"] > g["away"]["score"]
        p = min(max(d["home_win_prob"], 1e-6), 1 - 1e-6)
        win_ok += (p > 0.5) == hw
        ll -= math.log(p if hw else 1 - p)
        sll -= math.log(max(d["scores"].get(outcome(g), 0), 1e-6))
        exact += max(d["scores"], key=d["scores"].get) == outcome(g)
        # set handicap 1.5 on the favourite: favourite wins 3-0 or 3-1
        fav_home = p >= 0.5
        cover = (d["scores"]["3-0"] + d["scores"]["3-1"]) if fav_home else (d["scores"]["0-3"] + d["scores"]["1-3"])
        did = outcome(g) in (("3-0", "3-1") if fav_home else ("0-3", "1-3"))
        hcap_ok += (cover > 0.5) == did
        tot_err += abs(d["expected_total"] - sum(sum(s) for s in g["sets"]))
    return {"games": n, "win_accuracy": round(win_ok / n, 4), "log_loss": round(ll / n, 4),
            "set_score_log_loss": round(sll / n, 4), "set_score_exact": round(exact / n, 4),
            "handicap_1_5_accuracy": round(hcap_ok / n, 4), "total_points_mae": round(tot_err / n, 2),
            "home_team_won": round(sum(g["home"]["score"] > g["away"]["score"] for g, _ in rows) / n, 4)}


def train_volley(code):
    games = completed(code)
    best = None
    for values in itertools.product(*VOLLEY_GRID.values()):
        params = dict(zip(VOLLEY_GRID, values), regress=REGRESS)
        rows = volley_rows(games, params, TUNE)[WARMUP[code]:]
        loss = volley_metrics(rows)["set_score_log_loss"]
        if best is None or loss < best[0]:
            best = (loss, params, rows)
    _, params, rows = best
    totals = [sum(sum(s) for s in g["sets"]) - d["expected_total"] for g, d in rows]
    params["total_sigma"] = round(statistics.pstdev(totals), 2)
    params["total_bias"] = round(statistics.mean(totals), 2)
    test = volley_rows(games, params, TEST)
    report = {"league": code, "tuned_on": "2023-24", "tested_on": "2024-25", "params": params,
              "tune": volley_metrics(rows), "test": volley_metrics(test)}
    return params, report


def main():
    all_params = {}
    for code, fn in (("kbl", train_kbl), ("vmen", lambda: train_volley("vmen")),
                     ("vwomen", lambda: train_volley("vwomen"))):
        params, report = fn()
        all_params[code] = params
        write_json(KR / code / "backtest.json", report)
        print(json.dumps(report, indent=1))
    write_json(PARAMS_PATH, all_params)


if __name__ == "__main__":
    main()
