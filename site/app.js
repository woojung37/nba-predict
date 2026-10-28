"use strict";

const cache = {};
async function load(path) {
  if (!(path in cache)) {
    cache[path] = fetch("data/" + path).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  }
  return cache[path];
}

const app = document.getElementById("app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ko = (abbr) => TEAM_KO[abbr] || abbr;
const pct = (p) => (p == null ? "-" : Math.round(p * 100) + "%");
const num = (x, d = 1) => (x == null ? "-" : Number(x).toFixed(d));
const signed = (x) => (x == null ? "-" : (x > 0 ? "+" : "") + Number(x).toFixed(1));
const rec = (r) => (r ? `${r[0]}승 ${r[1]}패` : "-");
const STATUS_KO = { Out: "결장", Doubtful: "출전 어려움", Questionable: "출전 불투명", "Day-To-Day": "당일 결정" };
const statusKo = (s) => STATUS_KO[s] || s || "";
const SEASON_TYPE = { 2: "정규시즌", 3: "플레이오프", 5: "플레이인" };

function kst(iso, withDate = true) {
  const d = new Date(iso);
  const opts = { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false };
  if (withDate) Object.assign(opts, { month: "numeric", day: "numeric", weekday: "short" });
  return d.toLocaleString("ko-KR", opts);
}
function kstDay(iso) {
  return new Date(iso).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", weekday: "short" });
}

function teamLink(id, abbr, logo) {
  return `<a class="team" href="#/team/${id}">${logo ? `<img src="${esc(logo)}" alt="">` : ""}<span>${esc(ko(abbr))}</span></a>`;
}

function probBar(homeProb, homeAbbr, awayAbbr) {
  const h = Math.round(homeProb * 100);
  return `<div class="bar" role="img" aria-label="승리 확률 ${esc(ko(awayAbbr))} ${100 - h}%, ${esc(ko(homeAbbr))} ${h}%">
    <div class="away" style="width:${100 - h}%">${100 - h}%</div><div class="home" style="width:${h}%">${h}%</div></div>`;
}

async function teamsById() {
  const teams = (await load("teams.json")) || [];
  return Object.fromEntries(teams.map((t) => [t.id, t]));
}

// ---------- 경기 목록 ----------
async function viewGames() {
  const [games, teams] = await Promise.all([load("derived/upcoming.json"), teamsById()]);
  if (!games || !games.length) {
    app.innerHTML = `<h1>예정된 경기</h1><p class="muted">앞으로 이틀 안에 예정된 경기가 없어요.</p>`;
    return;
  }
  const byDay = {};
  for (const g of games) (byDay[kstDay(g.date)] ||= []).push(g);
  let html = `<h1>예정된 경기 <small>한국 시간</small></h1>`;
  for (const [day, list] of Object.entries(byDay)) {
    html += `<h2>${esc(day)}</h2><div class="cards">`;
    for (const g of list) {
      const p = g.prediction || g.pre_game_prediction;
      const fav = p && (p.home_margin >= 0 ? g.home : g.away);
      html += `<a class="card game" href="#/game/${g.id}">
        <div class="when">${kst(g.date, false)} · ${SEASON_TYPE[g.season_type] || ""}${g.state === "in" ? ' · <b class="live">진행 중</b>' : ""}</div>
        <div class="matchup">
          <div class="side">${logo(teams[g.away.id])}<b>${esc(ko(g.away.abbr))}</b><span class="muted">${esc(g.away.standing?.wins ?? 0)}-${esc(g.away.standing?.losses ?? 0)}</span></div>
          <div class="at">@</div>
          <div class="side">${logo(teams[g.home.id])}<b>${esc(ko(g.home.abbr))}</b><span class="muted">${esc(g.home.standing?.wins ?? 0)}-${esc(g.home.standing?.losses ?? 0)}</span></div>
        </div>
        ${p ? `${probBar(p.home_win_prob, g.home.abbr, g.away.abbr)}
        <div class="pred">예상 점수 <b>${Math.round(p.away_points)} : ${Math.round(p.home_points)}</b> · ${esc(ko(fav.abbr))} ${num(Math.abs(p.home_margin))}점 차 우세${p.total != null ? ` · 총점 ${num(p.total)}` : ""}</div>` : `<div class="muted">예측 준비 중</div>`}
      </a>`;
    }
    html += `</div>`;
  }
  app.innerHTML = html;
}
const logo = (t) => (t?.logo ? `<img class="logo" src="${esc(t.logo)}" alt="">` : "");

// ---------- 경기 상세 ----------
function factorLines(g) {
  const p = g.prediction, f = p.factors, H = ko(g.home.abbr), A = ko(g.away.abbr);
  const lines = [];
  const better = f.team_strength >= 0 ? H : A;
  lines.push([`팀 전력 (최근 경기력 반영 득실 기준)`, f.team_strength, `${better}이(가) 경기력에서 ${num(Math.abs(f.team_strength))}점 앞섬`]);
  if (f.home_court) lines.push([`홈 코트 이점`, f.home_court, `${H} 홈 경기`]);
  if (f.rest) {
    const tired = [p.back_to_back.home && H, p.back_to_back.away && A].filter(Boolean).join(", ");
    lines.push([`연전 피로`, f.rest, `${tired} 전날도 경기 (백투백)`]);
  }
  if (f.injuries) {
    const names = [...p.injury_impact.home, ...p.injury_impact.away].slice(0, 4).map((x) => x.name).join(", ");
    lines.push([`부상·결장 선수`, f.injuries, names]);
  }
  return lines;
}

async function viewGame(id) {
  const [games, teams] = await Promise.all([load("derived/upcoming.json"), teamsById()]);
  const g = (games || []).find((x) => x.id === id);
  if (!g) {
    app.innerHTML = `<p>경기를 찾을 수 없어요. 이미 끝난 경기일 수 있어요.</p><p><a href="#/">경기 목록으로</a></p>`;
    return;
  }
  const p = g.prediction || g.pre_game_prediction, H = g.home, A = g.away;
  let html = `<p><a href="#/">← 경기 목록</a></p>
  <h1>${esc(ko(A.abbr))} @ ${esc(ko(H.abbr))}</h1>
  <p class="muted">${kst(g.date)} (한국 시간) · ${esc(g.venue || "")}${g.neutral ? " · 중립 경기장" : ""}</p>`;
  if (p) {
    html += `<section class="panel">
      <h2>예측</h2>
      <div class="matchup big">
        <div class="side">${logo(teams[A.id])}<b>${esc(ko(A.abbr))}</b><span class="score">${Math.round(p.away_points)}</span><span>${pct(1 - p.home_win_prob)}</span></div>
        <div class="at">vs</div>
        <div class="side">${logo(teams[H.id])}<b>${esc(ko(H.abbr))}</b><span class="score">${Math.round(p.home_points)}</span><span>${pct(p.home_win_prob)}</span></div>
      </div>
      ${probBar(p.home_win_prob, H.abbr, A.abbr)}
      <p>예상 점수차: <b>${esc(ko(p.home_margin >= 0 ? H.abbr : A.abbr))} ${num(Math.abs(p.home_margin))}점 차</b>.
      경기 10번 중 8번은 점수차가 <b>${rangeText(p, H, A)}</b> 안에 들어올 것으로 봅니다.</p>
      ${p.factors ? `<h3>왜 이렇게 예측했나 <small>(${esc(ko(H.abbr))} 기준 점수)</small></h3>
      <table class="factors">${factorLines(g).map(([k, v, why]) => `<tr><td>${esc(k)}</td><td class="num ${v >= 0 ? "pos" : "neg"}">${signed(v)}</td><td class="muted">${esc(why)}</td></tr>`).join("")}
      <tr class="total"><td>합계 (예상 점수차)</td><td class="num">${signed(p.home_margin)}</td><td></td></tr></table>` : `<p class="muted">경기 시작 전 마지막 예측이에요.</p>`}
      ${g.odds?.details ? `<p class="muted">참고: 배팅 업체(${esc(g.odds.provider)}) 기준선 ${esc(g.odds.details)}</p>` : ""}
    </section>`;
  }
  if (p && p.total != null && p.sigma) html += linePanel(g);
  html += `<section class="panel"><h2>팀 비교</h2>${compareTable(g)}</section>`;
  html += `<section class="panel"><h2>상대전적 <small>(최근 시즌들)</small></h2>${h2hBlock(g)}</section>`;
  html += `<div class="two">${[A, H].map((t) => `<section class="panel"><h2>${esc(ko(t.abbr))} 부상자</h2>${injuryTable(t, p && p.injury_impact && p.injury_impact[t === H ? "home" : "away"])}</section>`).join("")}</div>`;
  html += `<div class="two">${[A, H].map((t) => `<section class="panel"><h2>${esc(ko(t.abbr))} 주요 선수</h2>${topPlayers(t)}</section>`).join("")}</div>`;
  app.innerHTML = html;
}

// 표준정규분포 누적확률 (Abramowitz-Stegun 근사)
function normCdf(x) {
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x / 2);
  return x >= 0 ? (1 + y) / 2 : (1 - y) / 2;
}

function linePanel(g) {
  const p = g.prediction, H = ko(g.home.abbr), A = ko(g.away.abbr);
  const short = (abbr) => ko(abbr).split(" ").pop();  // 표가 좁은 화면에서도 읽히도록 "셀틱스"처럼 줄임
  const h = short(g.home.abbr), a = short(g.away.abbr);
  const vl = p.vs_line || {};
  const spread = vl.spread ?? Math.round(-p.home_margin * 2) / 2 + 0.5;
  const ou = vl.over_under ?? Math.round(p.total) + 0.5;
  // [id, 기준선 설명, 선택, 확률 계산]
  const rows = [
    ["ml-h", () => "승패", () => `${h} 승`, () => p.home_win_prob],
    ["ml-a", () => "", () => `${a} 승`, () => 1 - p.home_win_prob],
    ["sp-h", () => "핸디캡", (sp) => `${h} ${sp > 0 ? "+" : ""}${sp}`, (sp) => normCdf((p.home_margin + sp) / p.sigma)],
    ["sp-a", () => "", (sp) => `${a} ${sp > 0 ? "−" : "+"}${Math.abs(sp)}`, (sp) => 1 - normCdf((p.home_margin + sp) / p.sigma)],
    ["ou-o", () => "언오버", (sp, o) => `오버 ${o}`, (sp, o) => normCdf((p.total - o) / p.total_sigma)],
    ["ou-u", () => "", (sp, o) => `언더 ${o}`, (sp, o) => 1 - normCdf((p.total - o) / p.total_sigma)],
  ];
  setTimeout(() => {
    const calc = () => {
      const sp = parseFloat(document.getElementById("ln-spread").value), o = parseFloat(document.getElementById("ln-ou").value);
      for (const [id, line, pick, prob] of rows) {
        const needs = id.startsWith("sp") ? sp : id.startsWith("ou") ? o : 0;
        const tr = document.getElementById("r-" + id);
        if (isNaN(needs)) { tr.hidden = true; continue; }
        tr.hidden = false;
        const pr = prob(sp, o);
        tr.querySelector(".l").textContent = line(sp, o);
        tr.querySelector(".k").textContent = pick(sp, o);
        tr.querySelector(".p").textContent = pct(pr);
        const odds = parseFloat(tr.querySelector("input").value);
        const ev = tr.querySelector(".ev");
        if (odds > 1) {
          const v = pr * odds - 1;
          ev.textContent = `${v >= 0 ? "+" : ""}${Math.round(v * 100)}%`;
          ev.className = "num ev " + (v >= 0 ? "pos" : "neg");
        } else { ev.textContent = "-"; ev.className = "num ev"; }
      }
    };
    document.querySelectorAll("#ln-panel input").forEach((el) => el.addEventListener("input", calc));
    if (document.getElementById("ln-panel")) calc();
  });
  return `<section class="panel" id="ln-panel"><h2>언오버 · 핸디캡 <small>(참고용)</small></h2>
    <p>예상 총점 <b>${num(p.total)}점</b> (10번 중 8번은 ${num(p.total_range80[0], 0)}~${num(p.total_range80[1], 0)}점),
    예상 점수차 <b>${esc(p.home_margin >= 0 ? H : A)} ${num(Math.abs(p.home_margin))}점</b>.</p>
    <div class="filters">
      <label>핸디캡 (${esc(H)} 기준, 예: −5.5) <input id="ln-spread" type="number" step="0.5" value="${spread}"></label>
      <label>기준 총점 <input id="ln-ou" type="number" step="0.5" value="${ou}"></label>
    </div>
    <div class="scroll"><table><thead><tr><th></th><th>선택</th><th class="num">확률</th><th class="num">배당</th><th class="num">기대값</th></tr></thead><tbody>
    ${rows.map(([id]) => `<tr id="r-${id}"><td class="l"></td><td class="k"></td><td class="num p"></td><td class="num"><input class="odds" type="number" step="0.01" min="1" placeholder="예: 1.85"></td><td class="num ev">-</td></tr>`).join("")}
    </tbody></table></div>
    <p class="muted">배당을 넣으면 기대값(모델 확률 × 배당 − 1)이 나와요. 플러스면 모델 기준으로 배당이 후한 편, 마이너스면 불리한 편이에요.
    ${vl.provider ? `기준선 기본값은 해외 업체(${esc(vl.provider)}) 값이에요. ` : ""}베트맨 기준선과 배당을 넣으면 바로 다시 계산돼요.
    모델은 기준선을 이긴다고 검증된 적이 없으니, 기대값이 플러스여도 참고만 하세요. 실제 기준선 적중 기록은 '예측 성적' 페이지에 쌓여요.</p>
  </section>`;
}

function rangeText(p, H, A) {
  const side = (m) => (m >= 0 ? `${ko(H.abbr)} ${num(m, 0)}점 승` : `${ko(A.abbr)} ${num(-m, 0)}점 승`);
  return `${side(p.margin_range80[0])} ~ ${side(p.margin_range80[1])}`;
}

function compareTable(g) {
  const a = g.away.stats || {}, h = g.home.stats || {};
  const rows = [
    ["시즌 성적", rec(a.record), rec(h.record)],
    ["홈 / 원정", `원정 ${rec(a.away_record)}`, `홈 ${rec(h.home_record)}`],
    ["최근 10경기", rec(a.last10_record), rec(h.last10_record)],
    ["평균 득점", num(a.ppg), num(h.ppg)],
    ["평균 실점", num(a.opp_ppg), num(h.opp_ppg)],
    ["평균 득실차", signed(a.avg_margin), signed(h.avg_margin)],
    ["공격 효율 (100포제션당 득점)", num(a.ortg), num(h.ortg)],
    ["수비 효율 (100포제션당 실점)", num(a.drtg), num(h.drtg)],
    ["경기 속도 (페이스)", num(a.pace), num(h.pace)],
    ["직전 경기 후 휴식일", restText(g.away.rest_days), restText(g.home.rest_days)],
    ["연속 기록", g.away.standing?.streak || "-", g.home.standing?.streak || "-"],
  ];
  return `<table><thead><tr><th></th><th>${esc(ko(g.away.abbr))}</th><th>${esc(ko(g.home.abbr))}</th></tr></thead>
    <tbody>${rows.map((r) => `<tr><td>${esc(r[0])}</td><td class="num">${esc(r[1])}</td><td class="num">${esc(r[2])}</td></tr>`).join("")}</tbody></table>`;
}
const restText = (d) => (d == null ? "-" : d === 0 ? "백투백" : `${d}일`);

function h2hBlock(g) {
  const h = g.head_to_head;
  if (!h || !h.games) return `<p class="muted">저장된 시즌에서 맞대결 기록이 없어요.</p>`;
  return `<p>${esc(ko(g.home.abbr))} 기준 <b>${h.wins}승 ${h.losses}패</b>, 평균 득실차 ${signed(h.avg_margin)}</p>
  <table><thead><tr><th>날짜</th><th>원정</th><th></th><th>홈</th></tr></thead><tbody>
  ${h.recent.map((m) => `<tr><td>${esc(m.date.slice(0, 10))}</td><td class="${m.away_score > m.home_score ? "win" : ""}">${esc(ko(m.away))} ${m.away_score}</td><td>@</td><td class="${m.home_score > m.away_score ? "win" : ""}">${esc(ko(m.home))} ${m.home_score}</td></tr>`).join("")}
  </tbody></table>`;
}

function injuryTable(t, impact) {
  const list = t.injuries || [];
  if (!list.length) return `<p class="muted">등록된 부상자가 없어요.</p>`;
  const eff = Object.fromEntries((impact || []).map((x) => [x.athlete_id, x.impact]));
  return `<table><thead><tr><th>선수</th><th>상태</th><th>부위</th><th>예측 영향</th></tr></thead><tbody>
  ${list.map((i) => `<tr><td>${esc(i.name)} <span class="muted">${esc(i.position || "")}</span></td><td><span class="tag ${esc(i.status)}">${esc(statusKo(i.status))}</span></td><td>${esc(i.injury || "-")}${i.return_date ? `<br><small class="muted">복귀 예상 ${esc(i.return_date)}</small>` : ""}</td><td class="num">${eff[i.athlete_id] != null ? signed(eff[i.athlete_id]) : "-"}</td></tr>`).join("")}
  </tbody></table>`;
}

function topPlayers(t) {
  const list = t.top_players || [];
  if (!list.length) return `<p class="muted">이번 시즌 기록이 아직 없어요.</p>`;
  return `<table><thead><tr><th>선수</th><th>경기</th><th>득점</th><th>리바운드</th><th>어시스트</th></tr></thead><tbody>
  ${list.map((p) => `<tr><td>${esc(p.name)} ${p.injury_status ? `<span class="tag ${esc(p.injury_status)}">${esc(statusKo(p.injury_status))}</span>` : ""}</td><td class="num">${p.gp}</td><td class="num">${num(p.pts)}</td><td class="num">${num(p.reb)}</td><td class="num">${num(p.ast)}</td></tr>`).join("")}
  </tbody></table>`;
}

// ---------- 순위 ----------
async function viewStandings() {
  const [st, power, teams] = await Promise.all([load("current/standings.json"), load("derived/power_ratings.json"), teamsById()]);
  const rank = Object.fromEntries((power || []).map((r, i) => [r.team_id, { ...r, rank: i + 1 }]));
  const confs = {};
  for (const s of st || []) (confs[s.conference] ||= []).push(s);
  let html = `<h1>순위</h1><p class="muted">전력 지수는 이 사이트 모델이 계산한 득실 기준 팀 전력이에요 (평균 팀 = 0).</p><div class="two">`;
  for (const [conf, list] of Object.entries(confs)) {
    html += `<section class="panel"><h2>${conf.includes("East") ? "동부 콘퍼런스" : "서부 콘퍼런스"}</h2><table>
      <thead><tr><th>#</th><th>팀</th><th>승</th><th>패</th><th>승률</th><th>최근10</th><th>연속</th><th>전력 지수</th></tr></thead><tbody>
      ${list.map((s) => `<tr><td>${s.seed ?? ""}</td><td>${teamLink(s.team_id, s.abbr, teams[s.team_id]?.logo)}</td><td class="num">${s.wins}</td><td class="num">${s.losses}</td><td class="num">${num(s.win_pct, 3)}</td><td class="num">${esc(s.last10 || "-")}</td><td class="num">${esc(s.streak || "-")}</td><td class="num">${rank[s.team_id] ? `${signed(rank[s.team_id].net)} <small class="muted">(${rank[s.team_id].rank}위)</small>` : "-"}</td></tr>`).join("")}
      </tbody></table></section>`;
  }
  app.innerHTML = html + `</div>`;
}

// ---------- 팀 ----------
async function viewTeam(id) {
  const [teams, tstats, players, rosters, injuries, st, upcoming] = await Promise.all([
    teamsById(), load("derived/team_stats.json"), load("derived/player_stats.json"), load("current/rosters.json"),
    load("current/injuries.json"), load("current/standings.json"), load("derived/upcoming.json")]);
  const meta = await load("meta.json");
  const games = (await load(`seasons/${meta?.season}/games.json`)) || [];
  const t = teams[id];
  if (!t) { app.innerHTML = `<p>팀을 찾을 수 없어요.</p>`; return; }
  const s = (tstats || {})[id] || {};
  const standing = (st || []).find((x) => x.team_id === id) || {};
  const avg = Object.fromEntries((players || []).filter((p) => p.team_id === id).map((p) => [p.athlete_id, p]));
  const inj = Object.fromEntries((injuries || []).filter((i) => i.team_id === id).map((i) => [i.athlete_id, i]));
  const roster = (rosters || []).filter((r) => r.team_id === id).sort((a, b) => (avg[b.athlete_id]?.pts ?? -1) - (avg[a.athlete_id]?.pts ?? -1));
  const mine = games.filter((g) => g.home.id === id || g.away.id === id);
  const done = mine.filter((g) => g.completed).slice(-10).reverse();
  const next = mine.filter((g) => g.state === "pre").slice(0, 5);
  const resultRow = (g) => {
    const home = g.home.id === id, me = home ? g.home : g.away, op = home ? g.away : g.home;
    return `<tr><td>${esc(g.date.slice(0, 10))}</td><td>${home ? "vs" : "@"} ${esc(ko(op.abbr))}</td><td class="${me.score > op.score ? "win" : "loss"}">${me.score > op.score ? "승" : "패"} ${me.score}-${op.score}</td></tr>`;
  };
  app.innerHTML = `<h1>${logo(t)} ${esc(ko(t.abbr))} <small>${esc(t.name)}</small></h1>
  <p>${standing.conference ? (standing.conference.includes("East") ? "동부" : "서부") : ""} ${standing.seed ? standing.seed + "위" : ""} · ${rec(s.record)} · 최근 10경기 ${rec(s.last10_record)}</p>
  <div class="stats">
    ${[["평균 득점", num(s.ppg)], ["평균 실점", num(s.opp_ppg)], ["평균 득실차", signed(s.avg_margin)], ["공격 효율", num(s.ortg)], ["수비 효율", num(s.drtg)], ["페이스", num(s.pace)]]
      .map(([k, v]) => `<div class="stat"><span>${k}</span><b>${v}</b></div>`).join("")}
  </div>
  <section class="panel"><h2>선수단 <small>(이번 시즌 경기당 평균)</small></h2><div class="scroll"><table>
    <thead><tr><th>#</th><th>선수</th><th>포지션</th><th>나이</th><th>키</th><th>경기</th><th>출전(분)</th><th>득점</th><th>리바운드</th><th>어시스트</th><th>야투%</th><th>3점%</th><th>상태</th></tr></thead><tbody>
    ${roster.map((r) => { const a = avg[r.athlete_id] || {}; const i = inj[r.athlete_id];
      return `<tr><td>${esc(r.jersey || "")}</td><td>${r.headshot ? `<img class="head" src="${esc(r.headshot)}" alt="">` : ""}${esc(r.name)}</td><td>${esc(r.position || "")}</td><td class="num">${esc(r.age ?? "")}</td><td>${esc(r.height || "")}</td><td class="num">${a.gp ?? 0}</td><td class="num">${num(a.min)}</td><td class="num">${num(a.pts)}</td><td class="num">${num(a.reb)}</td><td class="num">${num(a.ast)}</td><td class="num">${num(a.fg_pct)}</td><td class="num">${num(a.fg3_pct)}</td><td>${i ? `<span class="tag ${esc(i.status)}" title="${esc(i.injury || "")}">${esc(statusKo(i.status))}</span>` : ""}</td></tr>`; }).join("")}
  </tbody></table></div></section>
  <div class="two">
    <section class="panel"><h2>최근 경기</h2>${done.length ? `<table><tbody>${done.map(resultRow).join("")}</tbody></table>` : `<p class="muted">아직 경기가 없어요.</p>`}</section>
    <section class="panel"><h2>다음 경기</h2><table><tbody>${next.map((g) => { const home = g.home.id === id, op = home ? g.away : g.home;
      const up = (upcoming || []).find((u) => u.id === g.id);
      return `<tr><td>${kst(g.date)}</td><td>${home ? "vs" : "@"} ${esc(ko(op.abbr))}</td><td>${up?.prediction ? `<a href="#/game/${g.id}">승률 ${pct(home ? up.prediction.home_win_prob : up.prediction.away_win_prob)}</a>` : ""}</td></tr>`; }).join("")}</tbody></table></section>
  </div>`;
}

// ---------- 선수 ----------
let playerSort = "pts";
async function viewPlayers() {
  const [players, teams] = await Promise.all([load("derived/player_stats.json"), teamsById()]);
  const cols = [["pts", "득점"], ["reb", "리바운드"], ["ast", "어시스트"], ["stl", "스틸"], ["blk", "블록"], ["min", "출전(분)"], ["fg_pct", "야투%"], ["fg3_pct", "3점%"], ["ft_pct", "자유투%"], ["plus_minus", "+/-"]];
  app.innerHTML = `<h1>선수 기록 <small>이번 시즌 경기당 평균</small></h1>
  <div class="filters"><input id="q" type="search" placeholder="선수 이름 검색"> <select id="team"><option value="">전체 팀</option>${Object.values(teams).sort((a, b) => ko(a.abbr).localeCompare(ko(b.abbr), "ko")).map((t) => `<option value="${t.id}">${esc(ko(t.abbr))}</option>`).join("")}</select>
  <label><input id="min" type="checkbox" checked> 팀 경기 절반 이상 출전</label></div>
  <div class="scroll"><table id="pt"><thead><tr><th>#</th><th>선수</th><th>팀</th><th>경기</th>${cols.map(([k, l]) => `<th class="sort" data-k="${k}">${l}</th>`).join("")}</tr></thead><tbody></tbody></table></div>`;
  const maxGp = Math.max(1, ...(players || []).map((p) => p.gp));
  const render = () => {
    const q = document.getElementById("q").value.trim().toLowerCase(), tm = document.getElementById("team").value, minOn = document.getElementById("min").checked;
    const rows = (players || []).filter((p) => (!q || p.name.toLowerCase().includes(q)) && (!tm || p.team_id === tm) && (!minOn || p.gp >= maxGp / 2))
      .sort((a, b) => (b[playerSort] ?? -999) - (a[playerSort] ?? -999)).slice(0, 100);
    document.querySelector("#pt tbody").innerHTML = rows.map((p, i) => `<tr><td>${i + 1}</td><td>${esc(p.name)} <span class="muted">${esc(p.position || "")}</span></td><td><a href="#/team/${p.team_id}">${esc(ko(teams[p.team_id]?.abbr))}</a></td><td class="num">${p.gp}</td>${cols.map(([k]) => `<td class="num${k === playerSort ? " sorted" : ""}">${num(p[k])}</td>`).join("")}</tr>`).join("");
    document.querySelectorAll("th.sort").forEach((th) => th.classList.toggle("active", th.dataset.k === playerSort));
  };
  document.querySelectorAll("th.sort").forEach((th) => th.addEventListener("click", () => { playerSort = th.dataset.k; render(); }));
  ["q", "team", "min"].forEach((id) => document.getElementById(id).addEventListener("input", render));
  render();
}

// ---------- 예측 성적 ----------
function lineBox(tr) {
  const row = (name, r) => r && r.all.games ? `<tr><td>${name}</td><td class="num">${r.all.hits}/${r.all.games}</td><td class="num">${pct(r.all.hit_rate)}</td><td class="num">${r.confident.games ? `${r.confident.hits}/${r.confident.games} (${pct(r.confident.hit_rate)})` : "-"}</td></tr>` : `<tr><td>${name}</td><td colspan="3" class="muted">아직 기록 없음</td></tr>`;
  return `<h3>기준선 대비 적중 <small>(해외 업체 기준선, 무승부 제외)</small></h3>
  <table><thead><tr><th></th><th class="num">적중</th><th class="num">적중률</th><th class="num">확신 경기 (60% 이상)</th></tr></thead><tbody>
  ${row("핸디캡", tr.handicap)}${row("언오버", tr.over_under)}</tbody></table>
  ${tr.total_mae != null ? `<p class="muted">총점 평균 오차 ${num(tr.total_mae)}점. 참고로 기준선에서 수익을 내려면 보통 52~53% 이상 적중이 필요해요.</p>` : ""}`;
}
async function viewModel() {
  const [bt, tr] = await Promise.all([load("model/backtest.json"), load("model/track_record.json")]);
  const box = (m) => m ? `<div class="stats">
    <div class="stat"><span>경기 수</span><b>${m.games}</b></div>
    <div class="stat"><span>승패 적중률</span><b>${pct(m.win_accuracy)}</b></div>
    <div class="stat"><span>점수차 평균 오차</span><b>${num(m.margin_mae)}점</b></div>
    ${m.range80_coverage != null ? `<div class="stat"><span>80% 범위 안에 든 비율</span><b>${pct(m.range80_coverage)}</b></div>` : ""}
  </div>` : "";
  let html = `<h1>예측 성적</h1>
  <section class="panel"><h2>이번 시즌 실제 예측</h2>
  ${tr && tr.games ? box(tr) + lineBox(tr) : `<p class="muted">경기 전에 남긴 예측이 끝난 경기와 맞춰지면 여기에 쌓여요.</p>`}</section>`;
  if (bt) {
    html += `<section class="panel"><h2>지난 시즌 검증 <small>(${esc(bt.tested_on)}, 모델이 보지 않은 시즌)</small></h2>
    ${box(bt.test)}
    ${bt.test.total_mae != null ? `<p>총점(언오버) 예측: 평균 오차 <b>${num(bt.test.total_mae)}점</b>, 80% 범위 적중 ${pct(bt.test.total_range80_coverage)}.</p>` : ""}
    <p class="muted">비교: 무조건 홈팀 승리로 찍으면 ${pct(bt.baseline_home_team_wins)}. 정규시즌 ${pct(bt.test_regular_season.win_accuracy)}, 플레이오프 ${pct(bt.test_playoffs.win_accuracy)}.</p>
    <h3>확률은 믿을 만한가</h3>
    <p class="muted">모델이 우세 팀에 준 승률 구간별로, 실제로 우세 팀이 이긴 비율이에요. 두 숫자가 비슷할수록 확률이 정직하다는 뜻이에요.</p>
    <table><thead><tr><th>예측 승률</th><th>경기 수</th><th>실제 승리 비율</th></tr></thead><tbody>
    ${bt.calibration.map((c) => `<tr><td>${esc(c.bucket)}</td><td class="num">${c.games}</td><td class="num">${pct(c.favorite_won)}</td></tr>`).join("")}</tbody></table>
    <h3>모델 방식</h3>
    <ul>
      <li>팀마다 공격 지수와 수비 지수를 두고, 매 경기 결과로 조금씩 고칩니다 (최근 경기일수록 영향이 큼).</li>
      <li>홈 코트 이점 ${num(bt.params.hca)}점, 백투백(전날 경기) 팀 −${num(bt.params.b2b)}점을 반영합니다.</li>
      <li>부상자 명단의 주전급 선수가 빠지면, 그 선수의 최근 기여도만큼 점수를 깎습니다.</li>
      <li>시즌이 바뀌면 전력 지수를 평균 쪽으로 ${Math.round((1 - bt.params.regress) * 100)}% 되돌립니다.</li>
      <li>점수차 예측 오차의 표준편차는 약 ${num(bt.params.sigma)}점이라, 승률과 80% 범위는 이 값으로 계산합니다.</li>
    </ul></section>`;
  }
  app.innerHTML = html;
}

// ---------- 라우터 ----------
async function route() {
  const [, page, id] = (location.hash || "#/").split("/");
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#/${page || ""}`));
  window.scrollTo(0, 0);
  try {
    if (page === "game") await viewGame(id);
    else if (page === "team") await viewTeam(id);
    else if (page === "standings") await viewStandings();
    else if (page === "players") await viewPlayers();
    else if (page === "model") await viewModel();
    else await viewGames();
  } catch (e) {
    console.error(e);
    app.innerHTML = `<p>페이지를 그리는 중 문제가 생겼어요.</p>`;
  }
}
window.addEventListener("hashchange", route);
load("meta.json").then((m) => {
  if (m) document.getElementById("updated").textContent = `업데이트: ${new Date(m.updated_utc).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} (한국 시간)`;
});
route();
