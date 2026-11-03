"use strict";
// KBL · V리그 페이지. app.js의 load, esc, pct, num, signed, kst, kstDay, probBar, normCdf를 같이 씁니다.

const KR = {
  kbl: { name: "KBL", full: "KBL 남자농구", sport: "basketball" },
  vmen: { name: "V리그 남자", full: "V리그 남자배구", sport: "volleyball" },
  vwomen: { name: "V리그 여자", full: "V리그 여자배구", sport: "volleyball" },
};
const krLoad = (code, f) => load(`kr/${code}/${f}.json`);
const isVolley = (code) => KR[code].sport === "volleyball";

function krTabs(code, sub) {
  const t = (href, label, on) => `<button class="${on ? "on" : ""}" onclick="location.hash='${href}'">${label}</button>`;
  return `<div class="seg" style="margin:0 0 12px">
    ${Object.entries(KR).map(([c, l]) => t(`#/kr/${c}`, l.name, c === code && !sub)).join("")}
  </div>`;
}

function lowNote(g) {
  if (!g.low_confidence) return "";
  const d = g.data_games || {};
  return `<div class="muted" style="font-size:13px">⚠ 이번 시즌 데이터가 적어요 (${esc(g.away.ko)} ${d.away ?? 0}경기, ${esc(g.home.ko)} ${d.home ?? 0}경기). 지난 시즌 전력 위주의 예측이라 참고만 하세요.</div>`;
}

function setScoreLine(p, g) {
  const s = p.scores;
  const best = Object.entries(s).sort((a, b) => b[1] - a[1])[0];
  const [h, a] = best[0].split("-");
  return `가장 유력: <b>${a}:${h}</b> (${pct(best[1])}) · 총점 ${num(p.total)}`;
}

// ---------- 리그 메인 ----------
async function viewKr(code, sub, id) {
  if (!KR[code]) code = "kbl";
  if (sub === "game") return viewKrGame(code, id);
  const [up, recent, teams, tr, bt, meta] = await Promise.all([
    krLoad(code, "upcoming"), krLoad(code, "recent"), krLoad(code, "teams"),
    krLoad(code, "track_record"), krLoad(code, "backtest"), load("kr/meta.json")]);
  const V = isVolley(code);
  let html = `<h1>${esc(KR[code].full)} <small>한국 시간</small></h1>${krTabs(code)}`;
  html += `<p class="muted">무료 데이터(API-Sports)는 어제·오늘·내일 경기만 볼 수 있어서, 이번 시즌 기록은 2026년 11월 2일부터 매일 쌓고 있어요. 그 전 경기와 2025-26 시즌은 빠져 있고, 전력은 2024-25 시즌까지의 기록에서 출발합니다.</p>`;

  const open = (up || []).filter((g) => g.prediction);
  if (!open.length) html += `<section class="panel"><p class="muted">오늘·내일 예정된 경기가 없어요.</p></section>`;
  const byDay = {};
  for (const g of open) (byDay[kstDay(g.date)] ||= []).push(g);
  for (const [day, list] of Object.entries(byDay)) {
    html += `<h2>${esc(day)}</h2><div class="cards">`;
    for (const g of list) {
      const p = g.prediction;
      const fav = p.home_win_prob >= 0.5 ? g.home : g.away;
      html += `<a class="card game" href="#/kr/${code}/game/${g.id}">
        <div class="when">${kst(g.date, false)}${g.status !== "NS" ? ' · <b class="live">진행 중</b>' : ""}</div>
        <div class="matchup">
          <div class="side"><b>${esc(g.away.ko)}</b><span class="muted">원정</span></div>
          <div class="at">@</div>
          <div class="side"><b>${esc(g.home.ko)}</b><span class="muted">홈</span></div>
        </div>
        ${probBar(p.home_win_prob, g.home.ko, g.away.ko)}
        <div class="pred">${V ? setScoreLine(p, g)
          : `예상 점수 <b>${Math.round(p.away_points)} : ${Math.round(p.home_points)}</b> · ${esc(fav.ko)} ${num(Math.abs(p.home_margin))}점 차 우세 · 총점 ${num(p.total)}`}</div>
        ${lowNote(g)}
      </a>`;
    }
    html += `</div>`;
  }

  html += `<div class="two" style="margin-top:14px">`;
  html += `<section class="panel"><h2>순위·전력 <small>(11/2 이후 수집 경기 기준)</small></h2><table><thead><tr>
    <th>팀</th><th class="num">승</th><th class="num">패</th><th class="num">${V ? "득실 점수" : "득실"}</th><th class="num" title="모델 전력 지수">전력</th></tr></thead><tbody>
    ${(teams || []).map((t) => `<tr><td>${esc(t.ko)}</td><td class="num">${t.wins}</td><td class="num">${t.losses}</td>
      <td class="num">${t.wins + t.losses ? signed(t.points_for - t.points_against).replace(".0", "") : "-"}</td>
      <td class="num">${V ? signed(t.rating * 100) : signed(t.rating)}</td></tr>`).join("")}
    </tbody></table>
    <p class="muted" style="font-size:13px">전력: ${V ? "한 랠리를 따낼 힘을 리그 평균 대비로 나타낸 값(×100)" : "평균 팀 상대로 예상되는 점수차"}. 승패는 수집을 시작한 뒤의 경기만 셉니다.</p></section>`;

  html += `<section class="panel"><h2>예측 성적</h2>`;
  if (tr && tr.games) {
    html += `<div class="stats"><div class="stat"><span>실제 예측 경기</span><b>${tr.games}</b></div>
      <div class="stat"><span>승패 적중률</span><b>${pct(tr.win_accuracy)}</b></div>
      ${V ? `<div class="stat"><span>세트 스코어 정확히</span><b>${pct(tr.set_score_exact)}</b></div>`
          : `<div class="stat"><span>점수차 평균 오차</span><b>${num(tr.margin_mae)}점</b></div>`}</div>`;
  } else html += `<p class="muted">경기 전에 남긴 예측이 결과와 맞춰지면 여기에 쌓여요.</p>`;
  if (bt) {
    const m = bt.test;
    html += `<h3>지난 시즌 검증 <small>(2023-24로 맞추고 2024-25 ${m.games}경기로 확인)</small></h3>
    <div class="stats"><div class="stat"><span>승패 적중률</span><b>${pct(m.win_accuracy)}</b></div>
    ${V ? `<div class="stat"><span>세트 스코어 정확히</span><b>${pct(m.set_score_exact)}</b></div>
      <div class="stat"><span>세트 핸디 1.5 적중</span><b>${pct(m.handicap_1_5_accuracy)}</b></div>
      <div class="stat"><span>총점 평균 오차</span><b>${num(m.total_points_mae)}점</b></div>`
    : `<div class="stat"><span>점수차 평균 오차</span><b>${num(m.margin_mae)}점</b></div>
      <div class="stat"><span>총점 평균 오차</span><b>${num(m.total_mae)}점</b></div>`}</div>
    <p class="muted" style="font-size:13px">비교: 무조건 홈팀 승리로 찍으면 ${pct(m.home_team_won)}${V ? ", 세트 스코어(6가지)를 아무렇게나 찍으면 약 17%" : ""}.</p>`;
  }
  html += `</section></div>`;

  if (recent && recent.length) {
    html += `<section class="panel"><h2>최근 결과</h2><div class="scroll"><table><thead><tr><th>날짜</th><th>경기</th><th class="num">결과</th><th class="num">예측</th></tr></thead><tbody>
    ${recent.map((r) => {
      const p = r.pre_game_prediction;
      const hit = p ? (p.home_win_prob > 0.5) === (r.home_score > r.away_score) : null;
      return `<tr><td>${esc(kst(r.date))}</td><td>${esc(r.away.ko)} @ ${esc(r.home.ko)}</td>
        <td class="num"><b>${r.away_score} : ${r.home_score}</b>${r.sets ? `<br><span class="muted" style="font-size:12px">${r.sets.map((s) => `${s[1]}-${s[0]}`).join(", ")}</span>` : ""}</td>
        <td class="num">${p ? `${hit ? '<span class="pos">적중</span>' : '<span class="neg">실패</span>'}<br><span class="muted" style="font-size:12px">홈 ${pct(p.home_win_prob)}</span>` : '<span class="muted">-</span>'}</td></tr>`;
    }).join("")}</tbody></table></div></section>`;
  }
  html += modelNote(code, bt);
  if (meta?.updated_utc) html += `<p class="muted" style="font-size:13px">국내 리그 업데이트: ${new Date(meta.updated_utc).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}</p>`;
  app.innerHTML = html;
}

function modelNote(code, bt) {
  if (!bt) return "";
  const p = bt.params;
  if (!isVolley(code)) {
    return `<section class="panel"><h2>모델 방식</h2><ul>
      <li>NBA와 같은 방식이에요. 팀마다 공격·수비 지수를 두고 매 경기 결과로 조금씩 고칩니다.</li>
      <li>홈 코트 이점 ${num(p.hca)}점, 전날도 경기한 팀 −${num(p.b2b)}점을 반영합니다.</li>
      <li>점수차 오차의 표준편차가 약 ${num(p.sigma)}점이라 승률은 이 값으로 계산합니다.</li>
      <li>무료 데이터에는 선수 기록·부상자 명단이 없어서, 외국인 선수 결장 같은 소식은 아직 반영하지 못해요. 경기 전에 직접 확인하세요.</li>
    </ul></section>`;
  }
  return `<section class="panel"><h2>모델 방식</h2><ul>
    <li>팀마다 "랠리 한 점을 따낼 힘" 지수를 두고, 매 경기 실제로 딴 점수 비율로 조금씩 고칩니다.</li>
    <li>그 힘으로 한 세트가 25점(5세트는 15점), 듀스까지 어떻게 끝날지 정확히 계산한 뒤 세트를 이어 붙여 3:0, 3:1, 3:2 확률을 냅니다.</li>
    <li>세트마다 기복이 있다는 점도 넣었어요 (기복 크기 ${num(p.tau, 2)}). 홈 이점은 ${p.hca ? "작게" : "거의 없게"} 나왔습니다.</li>
    <li>무료 데이터에는 선수 기록이 없어서 주전 결장은 반영하지 못해요.</li>
  </ul></section>`;
}

// ---------- 경기 상세 ----------
async function viewKrGame(code, id) {
  const [up, all] = await Promise.all([krLoad(code, "upcoming"), krLoad(code, "games")]);
  const g = (up || []).find((x) => x.id === id);
  const back = `<p><a href="#/kr/${code}">← ${esc(KR[code].full)}</a></p>`;
  if (!g || !g.prediction) {
    app.innerHTML = back + `<p>경기를 찾을 수 없어요. 이미 끝난 경기일 수 있어요.</p>`;
    return;
  }
  const p = g.prediction, H = g.home.ko, A = g.away.ko, V = isVolley(code);
  let html = back + `<h1>${esc(A)} @ ${esc(H)}</h1><p class="muted">${kst(g.date)} (한국 시간) · ${esc(KR[code].full)}</p>
  <section class="panel"><h2>예측</h2>
    <div class="matchup big">
      <div class="side"><b>${esc(A)}</b>${V ? "" : `<span class="score">${Math.round(p.away_points)}</span>`}<span>${pct(1 - p.home_win_prob)}</span></div>
      <div class="at">vs</div>
      <div class="side"><b>${esc(H)}</b>${V ? "" : `<span class="score">${Math.round(p.home_points)}</span>`}<span>${pct(p.home_win_prob)}</span></div>
    </div>
    ${probBar(p.home_win_prob, H, A)}
    ${lowNote(g)}`;
  if (V) {
    const s = p.scores;
    const row = (label, k) => `<tr><td>${label}</td><td class="num">${pct(s[k])}</td></tr>`;
    html += `<div class="two" style="margin-top:12px">
      <div><h3>세트 스코어 확률</h3><table><tbody>
        ${row(`${esc(H)} 3:0`, "3-0")}${row(`${esc(H)} 3:1`, "3-1")}${row(`${esc(H)} 3:2`, "3-2")}
        ${row(`${esc(A)} 3:2`, "2-3")}${row(`${esc(A)} 3:1`, "1-3")}${row(`${esc(A)} 3:0`, "0-3")}
      </tbody></table></div>
      <div><h3>핸디캡·총점 <small>참고용</small></h3><table><tbody>
        <tr><td>${esc(H)} 세트 −1.5 (3:0·3:1 승)</td><td class="num">${pct(p.home_minus_1_5)}</td></tr>
        <tr><td>${esc(A)} 세트 −1.5 (3:0·3:1 승)</td><td class="num">${pct(p.away_minus_1_5)}</td></tr>
        <tr><td>풀세트(5세트)까지 갈 확률</td><td class="num">${pct(p.full_five_sets)}</td></tr>
        <tr><td>예상 세트 수</td><td class="num">${num(p.expected_sets, 1)}세트</td></tr>
        <tr><td>예상 총점 (양 팀 합)</td><td class="num"><b>${num(p.total)}</b></td></tr>
        <tr><td>총점 80% 범위</td><td class="num">${num(p.total_range80[0], 0)}–${num(p.total_range80[1], 0)}</td></tr>
      </tbody></table></div></div>
      <p class="muted" style="font-size:13px">한 세트를 ${esc(p.set_win_prob >= 0.5 ? H : A)}이(가) 가져갈 확률 ${pct(Math.max(p.set_win_prob, 1 - p.set_win_prob))}. 배구 총점은 세트 수(3~5세트)에 따라 크게 달라져서 범위가 넓어요.</p>`;
    html += `<h3>총점 기준선 계산기</h3><div class="filters">기준 총점 <input type="number" id="kr-ou" step="0.5" value="${Math.round(p.total) + 0.5}"> <span id="kr-ou-out"></span></div>`;
  } else {
    const f = p.factors;
    html += `<p>예상 점수차: <b>${esc(p.home_margin >= 0 ? H : A)} ${num(Math.abs(p.home_margin))}점 차</b>. 80% 범위 ${esc(H)} 기준 ${signed(p.margin_range80[0])} ~ ${signed(p.margin_range80[1])}.</p>
    <p>예상 총점 <b>${num(p.total)}</b> (80% 범위 ${num(p.total_range80[0], 0)}–${num(p.total_range80[1], 0)}).</p>
    <h3>왜 이렇게 예측했나 <small>${esc(H)} 기준 점수</small></h3><table class="factors"><tbody>
      <tr><td>팀 전력 (득실 기반)</td><td class="num">${signed(f.team_strength)}</td></tr>
      <tr><td>홈 코트</td><td class="num">${signed(f.home_court)}</td></tr>
      ${f.rest ? `<tr><td>연전 피로 (전날 경기)</td><td class="num">${signed(f.rest)}</td></tr>` : ""}
      <tr class="total"><td>합계</td><td class="num">${signed(p.home_margin)}</td></tr></tbody></table>
    <h3>핸디캡·언오버 계산기 <small>참고용</small></h3><div class="filters">
      ${esc(H)} 핸디 <input type="number" id="kr-sp" step="0.5" value="${Math.round(-p.home_margin * 2) / 2 + 0.5}">
      기준 총점 <input type="number" id="kr-ou" step="0.5" value="${Math.round(p.total) + 0.5}"></div>
      <p id="kr-ou-out"></p>
    <p class="muted" style="font-size:13px">외국인 선수·주전 결장은 아직 반영하지 못해요. 경기 전 KBL 공식 발표를 꼭 확인하세요.</p>`;
  }
  html += `</section>`;

  // 상대 전적 (수집된 경기 기준)
  const h2h = (all || []).filter((x) => x.completed && [x.home.id, x.away.id].includes(g.home.id) && [x.home.id, x.away.id].includes(g.away.id))
    .sort((a, b) => b.date.localeCompare(a.date));
  if (h2h.length) {
    const wins = h2h.filter((x) => (x.home.id === g.home.id) === (x.home.score > x.away.score)).length;
    html += `<section class="panel"><h2>상대 전적 <small>(2023-24 시즌 이후 수집된 경기)</small></h2>
    <p>${esc(H)} <b>${wins}승 ${h2h.length - wins}패</b></p><div class="scroll"><table><thead><tr><th>날짜</th><th>홈</th><th class="num">결과</th></tr></thead><tbody>
    ${h2h.slice(0, 12).map((x) => {
      const hk = x.home.id === g.home.id ? H : A, ak = x.home.id === g.home.id ? A : H;
      return `<tr><td style="white-space:nowrap">${new Date(x.date).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul", year: "2-digit", month: "numeric", day: "numeric" })}</td><td style="white-space:nowrap">${esc(hk)}</td>
        <td class="num">${esc(ak)} ${x.away.score} : ${x.home.score} ${esc(hk)}${x.sets ? `<br><span class="muted" style="font-size:12px">${x.sets.map((s) => `${s[1]}-${s[0]}`).join(", ")}</span>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div></section>`;
  }
  app.innerHTML = html;

  const ou = document.getElementById("kr-ou"), sp = document.getElementById("kr-sp"), out = document.getElementById("kr-ou-out");
  const calc = () => {
    const o = parseFloat(ou.value);
    let txt = "";
    if (sp) {
      const s = parseFloat(sp.value);
      if (!isNaN(s)) { const c = normCdf((p.home_margin + s) / p.sigma); txt += `${esc(H)} ${s > 0 ? "+" : ""}${s} 성공 ${pct(c)} / ${esc(A)} 쪽 ${pct(1 - c)}. `; }
    }
    if (!isNaN(o)) { const c = normCdf((p.total - o) / p.total_sigma); txt += `오버 ${pct(c)} / 언더 ${pct(1 - c)}`; }
    out.innerHTML = txt;
  };
  [ou, sp].forEach((el) => el && el.addEventListener("input", calc));
  calc();
}
