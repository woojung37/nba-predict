"""V-League match model.

Each team has a rating `a` on the log-odds scale of winning a single rally.
For a match the home side wins a rally with probability q = sigmoid(a_home -
a_away + hca + e), where e is per-set noise (teams have good and bad sets).
From q we get the exact distribution of every set score (to 25, fifth set to
15, win by two) and from the sets the match: 3-0 / 3-1 / 3-2 for either side,
set handicaps and total points.

After each match the ratings move a fraction k toward the observed share of
points won, so every prediction uses only earlier matches.
"""
import math
from collections import defaultdict
from functools import lru_cache

# Gauss-Hermite nodes/weights for E[f(Z)], Z ~ N(0,1) (probabilists' form)
_GH = [(-2.8570, 0.0112574), (-1.3556, 0.2220759), (0.0, 0.5333333),
       (1.3556, 0.2220759), (2.8570, 0.0112574)]
MAX_DEUCE = 12  # deuce rallies beyond this are lumped into the last score


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


@lru_cache(maxsize=None)
def set_scores(q, target):
    """{(home points, away points): probability} for one set."""
    # probability of reaching each score before anyone has won
    reach = defaultdict(float)
    reach[(0, 0)] = 1.0
    out = defaultdict(float)
    for total in range(0, 2 * (target - 1) + 1):
        for h in range(0, total + 1):
            a = total - h
            p = reach.get((h, a))
            if not p:
                continue
            for nh, na, pr in ((h + 1, a, q), (h, a + 1, 1 - q)):
                if nh == target and na <= target - 2:
                    out[(nh, na)] += p * pr
                elif na == target and nh <= target - 2:
                    out[(nh, na)] += p * pr
                elif nh <= target - 1 and na <= target - 1:
                    reach[(nh, na)] += p * pr
    deuce = reach[(target - 1, target - 1)]
    # from deuce: each pair of rallies ends it (q^2 or (1-q)^2) or ties again
    tie = 2 * q * (1 - q)
    for n in range(MAX_DEUCE):
        stay = deuce * tie ** n
        last = n == MAX_DEUCE - 1
        scale = 1 / (1 - tie) if last else 1.0
        out[(target + 1 + n, target - 1 + n)] += stay * q * q * scale
        out[(target - 1 + n, target + 1 + n)] += stay * (1 - q) ** 2 * scale
    return dict(out)


def set_summary(q, target, tau):
    """Set score distribution, averaged over set-to-set noise of size tau (log-odds)."""
    dist = defaultdict(float)
    for z, w in _GH:
        qq = sigmoid(logit(q) + tau * z)
        for (h, a), p in set_scores(round(qq, 3), target).items():
            dist[(h, a)] += w * p
    return dict(dist)


def match_distribution(q, tau):
    """Outcome probabilities and total points for a best-of-five match."""
    s25 = set_summary(q, 25, tau)
    s15 = set_summary(q, 15, tau)
    p_set = sum(p for (h, a), p in s25.items() if h > a)
    p5 = sum(p for (h, a), p in s15.items() if h > a)
    mean = lambda d, cond: (sum((h + a) * p for (h, a), p in d.items() if cond(h, a))
                            / max(1e-12, sum(p for (h, a), p in d.items() if cond(h, a))))
    pts_hw, pts_aw = mean(s25, lambda h, a: h > a), mean(s25, lambda h, a: h < a)
    pts5 = sum((h + a) * p for (h, a), p in s15.items())
    # walk through sets 1-4 tracking (home sets, away sets) and expected points
    states = {(0, 0): (1.0, 0.0)}  # -> (prob, prob-weighted points)
    final = {}
    for _ in range(4):
        nxt = defaultdict(lambda: [0.0, 0.0])
        for (h, a), (p, pts) in states.items():
            for won, pr, add in ((1, p_set, pts_hw), (0, 1 - p_set, pts_aw)):
                key = (h + won, a + 1 - won)
                nxt[key][0] += p * pr
                nxt[key][1] += (pts + p * add) * pr
        states = {}
        for k, (p, pts) in nxt.items():
            if 3 in k:
                final[k] = (final.get(k, (0, 0))[0] + p, final.get(k, (0, 0))[1] + pts)
            else:
                states[k] = (p, pts)
    p22, pts22 = states.get((2, 2), (0.0, 0.0))
    final[(3, 2)] = (p22 * p5, (pts22 + p22 * pts5) * p5)
    final[(2, 3)] = (p22 * (1 - p5), (pts22 + p22 * pts5) * (1 - p5))
    probs = {f"{h}-{a}": p for (h, a), (p, _) in final.items()}
    exp_total = sum(pts for _, pts in final.values())
    return {"home_win_prob": sum(p for (h, a), (p, _) in final.items() if h == 3),
            "scores": probs, "set_win_prob": p_set, "expected_total": exp_total,
            "expected_sets": sum((h + a) * p for (h, a), (p, _) in final.items())}


class VolleyRatings:
    def __init__(self, params):
        self.p = params
        self.a = defaultdict(float)
        self.season = None

    def new_season(self, season):
        if self.season is not None and season != self.season:
            factor = self.p["regress"] ** (season - self.season)
            for t in self.a:
                self.a[t] *= factor
        self.season = season

    def edge(self, home, away):
        return self.a[home] - self.a[away] + self.p["hca"]

    def predict(self, home, away):
        return match_distribution(round(sigmoid(self.edge(home, away)), 3), self.p["tau"])

    def update(self, home, away, sets):
        hp, ap = sum(s[0] for s in sets), sum(s[1] for s in sets)
        if not hp + ap:
            return
        err = logit(hp / (hp + ap)) - self.edge(home, away)
        self.a[home] += self.p["k"] * err
        self.a[away] -= self.p["k"] * err
        mean = sum(self.a.values()) / len(self.a)
        for t in self.a:
            self.a[t] -= mean


def replay(games, params, on_game=None):
    r = VolleyRatings(params)
    for g in games:
        if not g["completed"] or not g.get("sets"):
            continue
        r.new_season(g["season"])
        h, a = g["home"]["id"], g["away"]["id"]
        if on_game:
            on_game(g, r.predict(h, a))
        r.update(h, a, g["sets"])
    return r
