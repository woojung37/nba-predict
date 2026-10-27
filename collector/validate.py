"""Sanity checks on collected data. Exits non-zero if something looks wrong."""
import sys
from collections import defaultdict

from .store import DATA, read_csv, read_json


def check_season(season_path, problems):
    season = season_path.name
    games = read_json(season_path / "games.json", [])
    done = {g["id"]: g for g in games if g["completed"]}
    teams = read_csv(season_path / "team_games.csv")
    players = read_csv(season_path / "player_games.csv")
    boxed = defaultdict(int)
    for r in teams:
        boxed[r["game_id"]] += 1
    missing = [gid for gid in done if boxed.get(gid) != 2]
    if len(missing) > max(3, len(done) // 200):
        problems.append(f"{season}: {len(missing)} completed games without a box score")
    scored = defaultdict(int)
    for r in players:
        if r["pts"]:
            scored[(r["game_id"], r["team_id"])] += int(r["pts"])
    bad = [r for r in teams if r["pts"] and int(r["pts"]) != scored[(r["game_id"], r["team_id"])]]
    # ESPN occasionally drops a player's line from a box score; only a handful is expected
    if len(bad) > max(10, len(teams) // 100):
        problems.append(f"{season}: {len(bad)} team scores differ from summed player points")
    elif bad:
        print(f"{season}: note, {len(bad)} team scores differ from summed player points (source gaps)")
    for g in done.values():
        if g["home"]["score"] == g["away"]["score"]:
            problems.append(f"{season}: game {g['id']} is marked final with a tie")
    print(f"{season}: {len(games)} games, {len(done)} final, {len(teams)} team rows, "
          f"{len(players)} player rows, {len(missing)} missing box scores")


def main():
    problems = []
    if len(read_json(DATA / "teams.json", [])) != 30:
        problems.append("teams.json does not list 30 teams")
    for path in sorted((DATA / "seasons").glob("*")):
        check_season(path, problems)
    standings = read_json(DATA / "current" / "standings.json", [])
    if standings and len(standings) != 30:
        problems.append(f"standings list {len(standings)} teams")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
