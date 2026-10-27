"""NBA data collector.

  python -m collector.collect backfill --seasons 2025 2026 2027
  python -m collector.collect daily
  python -m collector.collect build

Seasons are named by the year they end in (2027 = 2026-27), as ESPN does.
"""
import argparse
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from model import predict

from . import derive, espn, parse
from .store import DATA, read_csv, read_json, season_dir, write_csv, write_json

ET = ZoneInfo("America/New_York")


def log(msg):
    print(msg, flush=True)


def today_et():
    return dt.datetime.now(ET).date()


def current_season(day=None):
    day = day or today_et()
    return day.year + 1 if day.month >= 8 else day.year


def season_days(season):
    day, end = dt.date(season - 1, 10, 1), dt.date(season, 6, 30)
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def load_teams(refresh=False):
    teams = None if refresh else read_json(DATA / "teams.json")
    if not teams:
        teams = parse.parse_teams(espn.teams())
        write_json(DATA / "teams.json", teams)
    return teams


def fetch_games(days, team_ids):
    days = list(days)
    with ThreadPoolExecutor(max_workers=4) as pool:
        boards = pool.map(espn.scoreboard, days)
        games = []
        for board in boards:
            games.extend(parse.parse_scoreboard(board, team_ids))
    return games


def merge_games(season, new_games):
    path = season_dir(season) / "games.json"
    games = {g["id"]: g for g in read_json(path, [])}
    for g in new_games:
        if g["season"] == season:
            games[g["id"]] = g
    merged = sorted(games.values(), key=lambda g: (g["date"], g["id"]))
    write_json(path, merged)
    return merged


def update_boxscores(season, games):
    """Fetch box scores for completed games we have not stored yet."""
    sdir = season_dir(season)
    team_rows = read_csv(sdir / "team_games.csv")
    player_rows = read_csv(sdir / "player_games.csv")
    have = {r["game_id"] for r in team_rows}
    todo = [g for g in games if g["completed"] and g["id"] not in have]
    if not todo:
        return
    log(f"  {season}: fetching {len(todo)} box scores")

    def one(game):
        try:
            return game, espn.summary(game["id"])
        except Exception as exc:  # keep going; the next run retries this game
            log(f"  ! box score {game['id']} failed: {exc}")
            return game, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (game, raw) in enumerate(pool.map(one, todo), 1):
            if raw is None:
                continue
            try:
                t, p = parse.parse_boxscore(raw, game)
            except (KeyError, TypeError, ValueError) as exc:
                log(f"  ! box score {game['id']} unreadable: {exc!r}")
                continue
            if len(t) == 2:
                team_rows.extend(t)
                player_rows.extend(p)
            if i % 200 == 0:
                log(f"    {i}/{len(todo)}")
    key = lambda r: (r["date"], r["game_id"])
    write_csv(sdir / "team_games.csv", sorted(team_rows, key=key), parse.TEAM_COLUMNS)
    write_csv(sdir / "player_games.csv", sorted(player_rows, key=key), parse.PLAYER_COLUMNS)


def cmd_backfill(args):
    teams = load_teams(refresh=True)
    team_ids = {t["id"] for t in teams}
    for season in args.seasons:
        path = season_dir(season) / "games.json"
        if args.force or not path.exists():
            log(f"{season}: fetching full schedule and results")
            games = merge_games(season, fetch_games(season_days(season), team_ids))
        else:
            games = read_json(path)
        log(f"{season}: {len(games)} games, {sum(g['completed'] for g in games)} completed")
        update_boxscores(season, games)


def cmd_daily(args):
    teams = load_teams(refresh=True)
    team_ids = {t["id"] for t in teams}
    season = current_season()
    if not (season_dir(season) / "games.json").exists():
        cmd_backfill(argparse.Namespace(seasons=[season], force=False))
    today = today_et()
    window = [today + dt.timedelta(days=d) for d in range(-3, 8)]
    games = merge_games(season, fetch_games(window, team_ids))
    update_boxscores(season, games)

    current = DATA / "current"
    write_json(current / "injuries.json", parse.parse_injuries(espn.injuries()))
    write_json(current / "standings.json", parse.parse_standings(espn.standings()))
    rosters = []
    for t in teams:
        rosters.extend(parse.parse_roster(espn.roster(t["id"]), t["id"]))
    write_json(current / "rosters.json", rosters)
    cmd_build(args)


def cmd_build(args):
    derive.build_all(DATA, current_season())
    predict.write_predictions(DATA, current_season())
    write_json(DATA / "meta.json", {
        "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "ESPN public API (site.api.espn.com)",
        "season": current_season(),
    })
    log("build done")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="collector")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="download whole seasons")
    b.add_argument("--seasons", type=int, nargs="+", required=True)
    b.add_argument("--force", action="store_true", help="re-download schedules")
    sub.add_parser("daily", help="refresh recent games, injuries, standings, rosters")
    sub.add_parser("build", help="rebuild derived files from stored data")
    args = ap.parse_args(argv)
    {"backfill": cmd_backfill, "daily": cmd_daily, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
