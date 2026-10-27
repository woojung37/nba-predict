# NBA 경기 분석·예측

NBA 전 경기의 상대전적, 부상자, 승률·예상 점수차를 매일 보여 주는 사이트입니다.

## 데이터 수집기 (`collector/`)

ESPN 공개 API(site.api.espn.com)에서 데이터를 받아 `data/`에 저장합니다. 파이썬 3.11 이상, 외부 패키지 없이 동작합니다.

```bash
python -m collector.collect backfill --seasons 2025 2026 2027  # 시즌 전체 (최초 1회)
python -m collector.collect daily                              # 최근 경기·부상자·순위·로스터 갱신
python -m collector.validate                                   # 데이터 점검
```

시즌 번호는 끝나는 해 기준입니다 (2027 = 2026-27 시즌).

| 파일 | 내용 |
| --- | --- |
| `data/teams.json` | 30개 팀 |
| `data/seasons/<시즌>/games.json` | 일정과 결과 (정규시즌, 플레이인, 플레이오프) |
| `data/seasons/<시즌>/team_games.csv` | 경기별 팀 기록 |
| `data/seasons/<시즌>/player_games.csv` | 경기별 선수 기록 |
| `data/current/injuries.json` | 현재 부상자 명단 |
| `data/current/standings.json` | 현재 순위 |
| `data/current/rosters.json` | 현재 로스터와 선수 정보 |
| `data/derived/team_stats.json` | 팀별 시즌 성적, 최근 10경기, 페이스, 공격·수비 효율 |
| `data/derived/player_stats.json` | 선수별 시즌 평균 |
| `data/derived/upcoming.json` | 향후 60시간 경기 (한국 시간, 상대전적, 부상자, 휴식일, 주요 선수) |

GitHub Actions(`.github/workflows/collect.yml`)가 매일 한국 시간 15:00과 06:30에 `daily`를 돌려 결과를 커밋합니다.
