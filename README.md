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

## 예측 모델 (`model/`)

팀마다 공격·수비 지수를 두고 매 경기 결과로 갱신합니다. 홈 코트, 백투백, 부상자(주전급 선수의 최근 기여도)를 반영해 예상 점수, 승률, 80% 점수차 범위를 냅니다.

```bash
python -m model.train   # 2024-25로 설정값을 고르고 2025-26으로 검증 → model/params.json, data/model/backtest.json
```

2025-26 검증 결과(모델이 보지 않은 시즌, 1,322경기): 승패 적중률 68%, 점수차 평균 오차 11.2점, 80% 범위 적중 80%, 총점 평균 오차 15.2점.

부가로 예상 총점(언오버)과 기준선 대비 확률(핸디캡·언오버)을 냅니다. 경기 페이지에서 기준선과 배당을 입력하면 확률과 기대값을 계산합니다. 기준선 대비 실제 적중 기록은 `data/model/track_record.json`에 쌓입니다.
`collector.collect daily`가 돌 때마다 예정 경기 예측이 `data/derived/upcoming.json`에 들어가고, 경기 전 예측은 `data/model/predictions_log.json`에 남아 실제 결과와 비교됩니다.

## 웹사이트 (`site/`)

정적 사이트(HTML/JS)로 `data/`의 JSON을 읽습니다. GitHub Actions가 데이터 갱신 후 GitHub Pages로 배포합니다.
로컬 확인: `site/`와 `data/`를 한 폴더에 모아 `python -m http.server`.
