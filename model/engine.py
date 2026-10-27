"""Point-in-time team ratings and game predictions.

Each team has an offense rating O (points scored above league average) and a
defense rating D (points allowed above league average). For a game:

    home points = L + O_home + D_away + hca/2 - fatigue/injury adjustments
    away points = L + O_away + D_home - hca/2 - ...

After each game the ratings move a fraction K toward the observed scores, so
every prediction only uses games played before it.
"""
import datetime as dt
import math
from collections import defaultdict, deque

from collector.store import DATA, read_csv, read_json

REPLACEMENT_GMSC = 5.0  # a bench replacement's typical game score
INJURY_WEIGHT = {"Out": 1.0, "Doubtful": 0.75, "Questionable": 0.5, "Day-To-Day": 0.35}


def game_score(r):
    f = lambda k: float(r[k] or 0)
    return (f("pts") + 0.4 * f("fgm") - 0.7 * f("fga") - 0.4 * (f("fta") - f("ftm"))
            + 0.7 * f("oreb") + 0.3 * f("dreb") + f("stl") + 0.7 * f("ast") + 0.7 * f("blk")
            - 0.4 * f("pf") - f("tov"))


def parse_time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def us_day(s):
    return (parse_time(s) - dt.timedelta(hours=5)).date()


class PlayerTracker:
    """Who is in each team's rotation, and how much each player is worth."""

    def __init__(self):
        self.recent = defaultdict(lambda: deque(maxlen=15))  # athlete -> game scores
        self.last_team = {}
        self.last_team_game = {}  # athlete -> index of team game when last played
        self.team_games = defaultdict(int)
        self.names = {}

    def value(self, athlete):
        scores = self.recent[athlete]
        return max(0.0, sum(scores) / len(scores) - REPLACEMENT_GMSC) if scores else 0.0

    def rotation(self, team):
        """Players expected to play for `team` next game, with their value."""
        n = self.team_games[team]
        return {a: self.value(a) for a, t in self.last_team.items()
                if t == team and n - self.last_team_game[a] <= 10 and len(self.recent[a]) >= 3}

    def missing_value(self, team, played):
        return sum(v for a, v in self.rotation(team).items() if a not in played)

    def record(self, team, rows):
        self.team_games[team] += 1
        for r in rows:
            self.recent[r["athlete_id"]].append(game_score(r))
            self.last_team[r["athlete_id"]] = team
            self.last_team_game[r["athlete_id"]] = self.team_games[team]
            self.names[r["athlete_id"]] = r["name"]


class Ratings:
    def __init__(self, params):
        self.p = params
        self.O = defaultdict(float)
        self.D = defaultdict(float)
        self.league = params.get("league_start", 113.0)
        self.season = None
        self.last_day = {}

    def new_season(self, season):
        if self.season is not None and season != self.season:
            for t in list(self.O):
                self.O[t] *= self.p["regress"]
                self.D[t] *= self.p["regress"]
        self.season = season

    def b2b(self, team, day):
        last = self.last_day.get(team)
        return 1 if last is not None and (day - last).days == 1 else 0

    def predict(self, home, away, neutral=False, b2b=(0, 0), missing=(0.0, 0.0)):
        p = self.p
        hca = 0.0 if neutral else p["hca"]
        home_pts = (self.league + self.O[home] + self.D[away] + hca / 2
                    - p["b2b"] * b2b[0] - p["injury"] * missing[0])
        away_pts = (self.league + self.O[away] + self.D[home] - hca / 2
                    - p["b2b"] * b2b[1] - p["injury"] * missing[1])
        return home_pts, away_pts

    def update(self, home, away, pred, actual, day):
        k, cap = self.p["k"], self.p.get("cap", 30)
        eh = max(-cap, min(cap, actual[0] - pred[0]))
        ea = max(-cap, min(cap, actual[1] - pred[1]))
        self.O[home] += k * eh
        self.D[away] += k * eh
        self.O[away] += k * ea
        self.D[home] += k * ea
        self.league += 0.01 * ((actual[0] + actual[1]) / 2 - self.league)
        self.last_day[home] = self.last_day[away] = day


def win_probability(margin, sigma):
    return 0.5 * (1 + math.erf(margin / (sigma * math.sqrt(2))))


def load_history(seasons=None):
    """Completed games in date order, with who actually played for each side."""
    seasons = seasons or sorted(int(p.name) for p in (DATA / "seasons").iterdir() if p.is_dir())
    games = []
    for s in seasons:
        sdir = DATA / "seasons" / str(s)
        played = defaultdict(list)
        for r in read_csv(sdir / "player_games.csv"):
            if r["dnp"] != "1" and r["min"] and int(r["min"]) > 0:
                played[(r["game_id"], r["team_id"])].append(r)
        for g in read_json(sdir / "games.json", []):
            if g["completed"] and g["home"]["score"] is not None:
                g = dict(g, played={side: played.get((g["id"], g[side]["id"])) for side in ("home", "away")})
                games.append(g)
    games.sort(key=lambda g: (g["date"], g["id"]))
    return games


def replay(games, params, on_game=None):
    """Walk through games in order, predicting each before learning from it."""
    ratings, players = Ratings(params), PlayerTracker()
    for g in games:
        ratings.new_season(g["season"])
        h, a = g["home"]["id"], g["away"]["id"]
        day = us_day(g["date"])
        b2b = (ratings.b2b(h, day), ratings.b2b(a, day))
        box = g.get("played") or {}
        has_box = bool(box.get("home")) and bool(box.get("away"))
        missing = (0.0, 0.0)
        if has_box:
            missing = tuple(players.missing_value(g[s]["id"], {r["athlete_id"] for r in box[s]})
                            for s in ("home", "away"))
        pred = ratings.predict(h, a, g["neutral"], b2b, missing)
        actual = (g["home"]["score"], g["away"]["score"])
        if on_game:
            on_game(g, pred, actual, {"b2b": b2b, "missing": missing})
        ratings.update(h, a, pred, actual, day)
        if has_box:
            players.record(h, box["home"])
            players.record(a, box["away"])
    return ratings, players
