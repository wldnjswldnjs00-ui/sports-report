/* 배당 분석 계산기: 배당 → 배당이 비슷했던 과거 경기의 실제 결과.
   유럽 축구·NBA·MLB 는 해외 배당 기록, 해외 기록이 없는 리그(KBL·WKBL·KOVO·K리그·KBO 등)는 베트맨 배당 기록으로 센다.
   데이터(/data/xbook.json)는 엔진의 xbook.py 와 같은 구간·같은 방식으로 센다. */
(function () {
  "use strict";
  var root = document.querySelector("[data-xo]");
  if (!root) return;
  var $ = function (s, r) { return (r || root).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || root).querySelectorAll(s)); };
  var NEED = 250;
  var D = null;
  var st = { sport: "soccer", mk: "main", grp: "x" };
  var DEF = {
    soccer: { h: "1.95", d: "3.10", a: "3.20", hl: "-0.5", ho: "1.80", ao: "1.80", ol: "2.5", o: "1.75", u: "1.75" },
    basketball: { h: "1.50", a: "2.25", hl: "-5.5", ho: "1.75", ao: "1.75", ol: "220.5", o: "1.75", u: "1.75" },
    baseball: { h: "1.65", a: "1.95", hl: "-1.5", ho: "1.95", ao: "1.60", ol: "8.5", o: "1.75", u: "1.75" }
  };
  /* 베트맨 배당 기준(해외 기록이 없는 리그) 기본값 */
  DEF.soccer_b = { h: "2.10", d: "3.10", a: "3.20", hl: "-1", ho: "3.40", hd: "3.40", ao: "1.75", ol: "2.5", o: "1.85", u: "1.65" };
  DEF.basketball_b = { h: "1.55", a: "2.15", hl: "-3.5", ho: "1.75", ao: "1.75", ol: "160.5", o: "1.75", u: "1.75" };
  DEF.baseball_b = { h: "1.80", a: "1.80", hl: "-1.5", ho: "2.10", ao: "1.55", ol: "8.5", o: "1.75", u: "1.75" };
  DEF.volleyball_b = { h: "1.45", a: "2.40", hl: "-1.5", ho: "1.75", ao: "1.75", ol: "180.5", o: "1.75", u: "1.75" };
  var V = JSON.parse(JSON.stringify(DEF));
  /* 종목별 리그 선택: x = 해외 배당 기록, 나머지 = 베트맨 배당 기록 */
  var LGS = {
    soccer: [["x", "유럽 리그"], ["kleague"], ["jleague"], ["soc_intl"], ["soc_etc"]],
    basketball: [["x", "NBA"], ["kbl"], ["wkbl"], ["bk_intl"]],
    baseball: [["x", "MLB"], ["kbo"], ["npb"]],
    volleyball: [["kovo_m"], ["kovo_w"], ["vb_intl"]]
  };
  function bm() { return st.grp !== "x"; }
  function vk() { return st.sport + (bm() ? "_b" : ""); }
  function gLabel(k) { var g = D && D.bb && D.bb.groups && D.bb.groups[k]; return g ? g.label : k; }
  function drawLgs() {
    var box = $("[data-xo-lgs]");
    if (!box) return;
    var list = LGS[st.sport] || [];
    if (!list.some(function (x) { return x[0] === st.grp; })) st.grp = list[0][0];
    box.innerHTML = "";
    list.forEach(function (x) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.dataset.xoLg = x[0];
      b.setAttribute("aria-pressed", String(x[0] === st.grp));
      var n = x[0] === "x" ? 0 : (((D && D.bb && D.bb.groups[x[0]]) || {}).n || {}).WL || 0;
      b.innerHTML = (x[1] || gLabel(x[0])) + ' <small>' + (x[0] === "x" ? "해외" : "베트맨") + "</small>";
      if (x[0] !== "x" && n) b.title = "베트맨 기록 " + n + "경기";
      b.addEventListener("click", function () { st.grp = x[0]; drawLgs(); drawInputs(); calc(); });
      box.appendChild(b);
    });
  }
  var LABEL = { soccer: "유럽 축구", basketball: "NBA", baseball: "MLB" };

  function num(x) { var v = parseFloat(String(x).replace(",", ".")); return isFinite(v) ? v : NaN; }
  function pct(x, d) { return (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  function fmtN(n) { return Number(n).toLocaleString("ko-KR"); }
  function bin(p, w) { var n = Math.round(1 / w); return Math.max(0, Math.min(n - 1, Math.floor(p / w + 1e-9))); }
  function fair(arr) {
    for (var i = 0; i < arr.length; i++) if (!(arr[i] > 1)) return null;
    var inv = arr.map(function (o) { return 1 / o; }), s = inv.reduce(function (a, b) { return a + b; }, 0);
    return inv.map(function (v) { return v / s; });
  }
  function add(a, b) { return a ? a.map(function (x, i) { return x + b[i]; }) : b.slice(); }
  function gather(t, keysAt) {
    var acc = null;
    for (var r = 0; r <= 3; r++) {
      acc = null;
      keysAt(r).forEach(function (k) { if (t[k]) acc = add(acc, t[k]); });
      if (acc && acc[0] >= NEED) return acc;
    }
    return acc && acc[0] >= NEED / 3 ? acc : null;
  }
  function ring(i, r) { var o = []; for (var a = -r; a <= r; a++) o.push(String(i + a)); return o; }
  function sgn(x) { return (x > 0 ? "+" : "") + x; }
  function near(a, b) { return Math.abs(a - b) < 1e-9; }

  /* 분포(값 v 의 경기 수)에서 "v + L > 0" 비율. 정수 기준점은 동률(적중특례)을 빼고, 쿼터(.25·.75)는 양옆 반 기준점의 평균 */
  function rate(hist, valueAt, L) {
    var q = Math.round(L * 4);
    if (Math.abs(q) % 2 === 1) return (rate(hist, valueAt, L - 0.25) + rate(hist, valueAt, L + 0.25)) / 2;
    var w = 0, p = 0, n = 0;
    hist.forEach(function (c, i) { var x = valueAt(i) + L; n += c; if (x > 1e-9) w += c; else if (Math.abs(x) < 1e-9) p += c; });
    return n - p > 0 ? w / (n - p) : NaN;
  }
  /* 해외 기준점에서 해외 확률이 p 와 비슷했던 칸들을 모은다(오차 2%p부터 넓혀 가며 표본 300 이상) */
  function similar(cells, fit, p, need) {
    for (var tol = 0.02; tol <= 0.061; tol += 0.01) {
      var acc = null;
      cells.forEach(function (c) { var r = fit(c); if (isFinite(r) && Math.abs(r - p) <= tol) acc = add(acc, c.row); });
      if (acc && acc[0] >= (need || 300)) return acc;
    }
    return null;
  }

  /* ───── 입력칸 ───── */
  /* 입력은 모두 베트맨 배당(사람들이 보고 사는 배당). 해외 기록 리그는 발행처 몫을 걷어낸 확률로 바꿔 해외 기록과 맞춰 본다 */
  var FIELDS = {
    soccer: { main: [["h", "승"], ["d", "무"], ["a", "패"]],
      hcp: [["hl", "핸디 기준점 (홈)"], ["ho", "핸디승"], ["hd", "핸디무"], ["ao", "핸디패"]],
      ou: [["ol", "기준점"], ["o", "오버"], ["u", "언더"]] },
    us: { main: [["h", "승"], ["a", "패"]],
      hcp: [["hl", "핸디 기준점 (홈)"], ["ho", "핸디승"], ["ao", "핸디패"]],
      ou: [["ol", "기준점"], ["o", "오버"], ["u", "언더"]] }
  };
  FIELDS.bsoc = { main: [["h", "승"], ["d", "무"], ["a", "패"]],
    hcp: [["hl", "핸디 기준점 (홈)"], ["ho", "핸디승"], ["hd", "핸디무"], ["ao", "핸디패"]],
    ou: [["ol", "기준점"], ["o", "오버"], ["u", "언더"]] };
  FIELDS.bus = { main: [["h", "승"], ["a", "패"]],
    hcp: [["hl", "핸디 기준점 (홈)"], ["ho", "핸디승"], ["ao", "핸디패"]],
    ou: [["ol", "기준점"], ["o", "오버"], ["u", "언더"]] };
  function fields() {
    if (bm()) return (st.sport === "soccer" ? FIELDS.bsoc : FIELDS.bus)[st.mk];
    return (st.sport === "soccer" ? FIELDS.soccer : FIELDS.us)[st.mk];
  }
  function drawInputs() {
    var box = $("[data-xo-inputs]");
    box.innerHTML = "";
    fields().forEach(function (f) {
      var lab = document.createElement("label"), sp = document.createElement("span"), inp = document.createElement("input");
      sp.textContent = f[1];
      inp.className = "input"; inp.type = "text"; inp.inputMode = "decimal"; inp.autocomplete = "off";
      inp.value = V[vk()][f[0]] || ""; inp.dataset.k = f[0];
      inp.setAttribute("aria-label", f[1]);
      inp.addEventListener("input", function () { V[vk()][f[0]] = inp.value; calc(); });
      lab.appendChild(sp); lab.appendChild(inp); box.appendChild(lab);
    });
    box.style.setProperty("--cols", fields().length);
    $("[data-xo-main]").textContent = st.sport === "soccer" ? "승무패" : "승패";
    var hint = $(".xo-hint");
    if (hint) hint.textContent = bm()
      ? "이 리그는 해외 배당 기록이 없어 베트맨 배당 기록으로 셉니다. 베트맨 배당을 그대로 넣으세요. 핸디캡·언더오버는 기준점과 상관없이 배당 확률이 비슷했던 지난 경기로 셉니다."
      : "베트맨 배당을 그대로 넣으세요. 발행처 몫을 걷어낸 확률로 바꿔, 해외 배당 기록에서 확률이 비슷했던 경기와 맞춰 봅니다. 핸디캡·언더오버는 베트맨 기준점을 넣습니다. '오늘 경기에서 불러오기'를 쓰면 자동으로 채워집니다.";
  }

  /* ───── 결과 그리기 ───── */
  function out(html) { $("[data-xo-out]").innerHTML = html; }
  function head(n, sub) { return '<div class="xo-head"><b>비슷한 경기 ' + fmtN(n) + '개</b><span>' + sub + "</span></div>"; }
  function bars(rows) {
    return '<ul class="xo-bars">' + rows.map(function (r) {
      var d = (r.real - r.imp) * 100, cls = Math.abs(d) < 1 ? "flat" : d > 0 ? "up" : "down";
      return '<li><span class="xo-k">' + r.k + '</span><span class="xo-bar"><i style="width:' + (r.real * 100).toFixed(1) + '%"></i></span><b>' + pct(r.real) +
        '</b><small>배당 확률 ' + pct(r.imp) + ' · <em class="' + cls + '">' + (d >= 0 ? "+" : "") + d.toFixed(1) + "%p</em></small></li>";
    }).join("") + "</ul>";
  }
  var SUBJ = { "승": "승이", "패": "패가", "핸디승": "핸디승이", "핸디무": "핸디무가", "핸디패": "핸디패가", "홈승": "홈승이", "무": "무승부가", "원정승": "원정승이", "홈": "홈이", "원정": "원정이", "오버": "오버가", "언더": "언더가" };
  function say(rows) {
    var big = rows.slice().sort(function (a, b) { return Math.abs(b.real - b.imp) - Math.abs(a.real - a.imp); })[0];
    var d = (big.real - big.imp) * 100;
    if (Math.abs(d) < 1) return '<p class="xo-say">배당이 말한 확률과 실제 결과가 거의 같았습니다(차이 1%p 미만). 이 구도에서는 배당을 그대로 믿어도 됩니다.</p>';
    return '<p class="xo-say">' + (SUBJ[big.k] || big.k) + " 배당이 말한 것보다 <b>" + Math.abs(d).toFixed(1) + "%p " + (d > 0 ? "더 자주" : "덜") + "</b> 나왔습니다." +
      (Math.abs(d) >= 3 ? " 차이가 큰 편입니다." : "") + "</p>";
  }
  function table(cols, rows) {
    return '<div class="tblw"><table class="tbl xo-tbl"><thead><tr><th>기준점</th>' + cols.map(function (c) { return '<th class="n">' + c + "</th>"; }).join("") +
      "</tr></thead><tbody>" + rows.map(function (r) {
        var best = Math.max.apply(null, r.v);
        return "<tr" + (r.hl ? ' class="is-hl"' : "") + "><td>" + r.line + (r.hl ? ' <small class="xo-tag">입력 기준점</small>' : "") + "</td>" + r.v.map(function (v) {
          return '<td class="n"><span class="xo-cell' + (v === best ? " is-top" : "") + '"><i style="width:' + (v * 100).toFixed(1) + '%"></i><b>' + pct(v) + "</b></span></td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }
  function need(msg) { out('<p class="none">' + msg + "</p>"); }
  function lineSet(center, step, k) { var o = []; for (var i = -k; i <= k; i++) o.push(Math.round((center + i * step) * 4) / 4); return o; }

  function calc() {
    if (!D) return;
    if (bm()) return calcBM(V[vk()]);
    return st.sport === "soccer" ? calcSoccer(V.soccer) : calcUS(V[st.sport]);
  }

  /* 베트맨 배당 기준: 베트맨 배당 확률이 비슷했던 지난 경기(같은 리그 → 부족하면 종목 전체) */
  function calcBM(v) {
    var B = D.bb;
    if (!B || !B.data) return need("베트맨 기록을 모으는 중입니다.");
    var MK = st.mk === "main" ? "WL" : st.mk === "hcp" ? "HANDICAP" : "OU";
    var f, names;
    if (MK === "OU") {
      f = fair([num(v.o), num(v.u)]); names = ["오버", "언더"];
      if (!f) return need("오버·언더 배당을 1보다 큰 숫자로 넣으세요.");
    } else {
      var three = st.sport === "soccer" && num(v[MK === "WL" ? "d" : "hd"]) > 1;
      var arr = MK === "WL" ? (three ? [num(v.h), num(v.d), num(v.a)] : [num(v.h), num(v.a)]) : (three ? [num(v.ho), num(v.hd), num(v.ao)] : [num(v.ho), num(v.ao)]);
      f = fair(arr);
      names = MK === "WL" ? (three ? ["승", "무", "패"] : ["승", "패"]) : (three ? ["핸디승", "핸디무", "핸디패"] : ["핸디승", "핸디패"]);
      if (!f) return need((MK === "WL" ? "승·패" : "핸디승·핸디패") + " 배당을 1보다 큰 숫자로 넣으세요.");
    }
    var w = B.w || 0.05, need0 = B.need || 40, i0 = bin(f[0], w), gTot = 0;
    var keys = [st.grp, "all_" + st.sport];
    for (var ki = 0; ki < keys.length; ki++) {
      var k = keys[ki], t = (B.data[k] || {})[MK] || {}, tot = 0;
      Object.keys(t).forEach(function (x) { tot += t[x][0]; });
      if (ki === 0) gTot = tot;
      if (ki === 0 && tot < (B.min_group || 25)) continue;
      for (var r = 0; r <= 3; r++) {
        var acc = null;
        ring(i0, r).forEach(function (x) { if (t[x]) acc = add(acc, t[x]); });
        if (acc && acc[0] >= need0) {
          var n = acc[0], rows;
          var n2 = acc[1] + acc[3] || 1;  // 두 칸 마켓은 적중특례(무 칸)를 빼고 센다
          if (MK === "OU") rows = [{ k: "오버", real: acc[1] / n2, imp: f[0] }, { k: "언더", real: acc[3] / n2, imp: f[1] }];
          else if (names.length === 3) rows = [{ k: names[0], real: acc[1] / n, imp: f[0] }, { k: names[1], real: acc[2] / n, imp: f[1] }, { k: names[2], real: acc[3] / n, imp: f[2] }];
          else rows = [{ k: names[0], real: acc[1] / n2, imp: f[0] }, { k: names[1], real: acc[3] / n2, imp: f[1] }];
          var sub = gLabel(k) + " · 베트맨 배당 확률 " + f.map(function (x) { return pct(x, 0); }).join(" · ");
          var note = ki > 0 ? '<p class="fine xo-note">' + gLabel(st.grp) + " 기록이 아직 " + gTot + "경기라 이 배당 구도는 " + gLabel(k) + " 베트맨 기록으로 계산했습니다. 기록은 자동 업데이트마다 쌓입니다.</p>" : "";
          return out(head(n, sub) + bars(rows) + say(rows) + note);
        }
      }
    }
    return need("이 배당 구도는 베트맨 지난 기록이 부족합니다. 기록은 자동 업데이트마다 쌓입니다.");
  }

  function calcSoccer(v) {
    var S = D.soc;
    if (!S) return need("축구 기록을 모으는 중입니다.");
    if (st.mk === "main") {
      var f = fair([num(v.h), num(v.d), num(v.a)]);
      if (!f) return need("베트맨 승무패 배당(승·무·패)을 1보다 큰 숫자로 넣으세요.");
      var bi = bin(f[0], S.w), bj = bin(f[2], S.w);
      var acc = gather(S.pair, function (r) { var o = []; for (var a = -r; a <= r; a++) for (var b = -r; b <= r; b++) o.push((bi + a) + "|" + (bj + b)); return o; });
      if (!acc) return need("이 배당 구도는 과거 기록이 부족합니다.");
      var n = acc[0], rows = [{ k: "홈승", real: acc[1] / n, imp: f[0] }, { k: "무", real: acc[2] / n, imp: f[1] }, { k: "원정승", real: acc[3] / n, imp: f[2] }];
      return out(head(n, "유럽 축구 · 베트맨 배당 확률(몫 제외) " + pct(f[0], 0) + "·" + pct(f[1], 0) + "·" + pct(f[2], 0)) + bars(rows) + say(rows));
    }
    var M = S.dm;
    if (st.mk === "hcp") {
      var L = num(v.hl), hd3 = num(v.hd), three = isFinite(hd3) && hd3 > 1 && Math.abs(L % 1) < 1e-9;
      var fh = three ? fair([num(v.ho), hd3, num(v.ao)]) : fair([num(v.ho), num(v.ao)]);
      if (!isFinite(L) || !fh) return need("베트맨 핸디 기준점(홈 기준, 예: -1)과 핸디승·핸디패 배당(정수 기준점이면 핸디무까지)을 넣으세요.");
      var cells = Object.keys(S.pair).map(function (k) { var r = S.pair[k]; return { row: [r[4]].concat(r.slice(5)) }; }).filter(function (c) { return c.row[0] >= 40; });
      if (!cells.length) return need("축구 핸디캡은 득점 차 기록을 받는 중입니다. 자동 업데이트로 하루 안에 채워집니다.");
      var dv = function (i) { return i - M; };
      if (three) {
        // 베트맨 축구 정수 핸디는 승·무·패 3갈래: 무(점수 차가 기준점과 같음)를 따로 센다
        var r3 = function (h, x) { var w = 0, p = 0, n = 0; h.forEach(function (c, i) { var y = dv(i) + x; n += c; if (y > 1e-9) w += c; else if (Math.abs(y) < 1e-9) p += c; }); return n ? [w / n, p / n, (n - w - p) / n] : null; };
        var h3 = similar(cells, function (c) { var q = r3(c.row.slice(1), L); return q ? q[0] : NaN; }, fh[0]);
        if (!h3) return need("이 핸디 구도는 과거 기록이 부족합니다.");
        var q3 = r3(h3.slice(1), L), rr3 = [{ k: "핸디승", real: q3[0], imp: fh[0] }, { k: "핸디무", real: q3[1], imp: fh[1] }, { k: "핸디패", real: q3[2], imp: fh[2] }];
        var rows3h = lineSet(L, 1, 2).map(function (x) { var q = r3(h3.slice(1), x); return { line: "홈 " + sgn(x), v: q, hl: near(x, L) }; });
        return out(head(h3[0], "유럽 축구 · 베트맨 핸디 홈 " + sgn(L) + " · 핸디승 확률(몫 제외) " + pct(fh[0], 0)) + bars(rr3) + say(rr3) + table(["핸디승", "핸디무", "핸디패"], rows3h));
      }
      var hist = similar(cells, function (c) { return rate(c.row.slice(1), dv, L); }, fh[0]);
      if (!hist) return need("이 핸디 구도는 과거 기록이 부족합니다.");
      var hd = hist.slice(1), rows2 = lineSet(L, 1, 2).map(function (x) { var p = rate(hd, dv, x); return { line: "홈 " + sgn(x), v: [p, 1 - p], hl: near(x, L) }; });
      var pr = rate(hd, dv, L), rr = [{ k: "핸디승", real: pr, imp: fh[0] }, { k: "핸디패", real: 1 - pr, imp: fh[1] }];
      return out(head(hist[0], "유럽 축구 · 베트맨 핸디 홈 " + sgn(L) + " · 핸디승 확률(몫 제외) " + pct(fh[0], 0)) + bars(rr) + say(rr) + table(["핸디승", "핸디패"], rows2));
    }
    var OL = num(v.ol), fo = fair([num(v.o), num(v.u)]);
    if (!(OL > 0) || !fo) return need("베트맨 언더오버 기준점(예: 2.5)과 오버·언더 배당을 넣으세요.");
    var gcells = Object.keys(S.goals).map(function (k) { return { row: S.goals[k] }; }).filter(function (c) { return c.row[0] >= 40; });
    var gv = function (i) { return i; };
    var over = function (h, x) { return rate(h, function (i) { return i; }, -x); };
    var gh = similar(gcells, function (c) { return over(c.row.slice(1), OL); }, fo[0]);
    if (!gh) return need("이 언더오버 구도는 과거 기록이 부족합니다.");
    var g = gh.slice(1), avg = 0;
    g.forEach(function (c, i) { avg += i * c; });
    var lines = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5];
    if (lines.indexOf(OL) < 0) { lines.push(OL); lines.sort(function (a, b) { return a - b; }); }
    var rows3 = lines.map(function (x) { var p = over(g, x); return { line: x, v: [p, 1 - p], hl: near(x, OL) }; });
    var po = over(g, OL), ro = [{ k: "오버", real: po, imp: fo[0] }, { k: "언더", real: 1 - po, imp: fo[1] }];
    void gv;
    return out(head(gh[0], "유럽 축구 · 베트맨 " + OL + " 오버 확률(몫 제외) " + pct(fo[0], 0) + " · 평균 " + (avg / gh[0]).toFixed(2) + "골") + bars(ro) + say(ro) + table(["오버", "언더"], rows3));
  }

  function calcUS(v) {
    var B = D[st.sport];
    if (!B) return need(LABEL[st.sport] + " 기록을 모으는 중입니다.");
    var M = B.m, mv = function (i) { return i - M; };
    if (st.mk === "main") {
      var f = fair([num(v.h), num(v.a)]);
      if (!f) return need("베트맨 승패 배당(승·패)을 1보다 큰 숫자로 넣으세요.");
      var i0 = bin(f[0], B.w), h = gather(B.wl, function (r) { return ring(i0, r); });
      if (!h) return need("이 배당 구도는 과거 기록이 부족합니다.");
      var pw = rate(h.slice(1), mv, 0), rws = [{ k: "홈승", real: pw, imp: f[0] }, { k: "원정승", real: 1 - pw, imp: f[1] }];
      return out(head(h[0], LABEL[st.sport] + " · 베트맨 배당 확률(몫 제외) " + pct(f[0], 0) + " 대 " + pct(f[1], 0)) + bars(rws) + say(rws));
    }
    if (st.mk === "hcp") {
      var L = num(v.hl), fh = fair([num(v.ho), num(v.ao)]);
      if (!isFinite(L) || !fh) return need("베트맨 핸디 기준점(홈 기준, 예: -5.5)과 핸디승·핸디패 배당을 넣으세요.");
      var cells = Object.keys(B.wl).map(function (k) { return { row: B.wl[k] }; }).filter(function (c) { return c.row[0] >= 40; });
      var hist = similar(cells, function (c) { return rate(c.row.slice(1), mv, L); }, fh[0]);
      if (!hist) return need("이 핸디 구도는 과거 기록이 부족합니다.");
      var hd = hist.slice(1), step = st.sport === "basketball" ? 2 : 1, k = st.sport === "basketball" ? 4 : 2;
      var rows2 = lineSet(L, step, k).map(function (x) { var p = rate(hd, mv, x); return { line: "홈 " + sgn(x), v: [p, 1 - p], hl: near(x, L) }; });
      var pr = rate(hd, mv, L), rr = [{ k: "핸디승", real: pr, imp: fh[0] }, { k: "핸디패", real: 1 - pr, imp: fh[1] }];
      return out(head(hist[0], LABEL[st.sport] + " · 베트맨 핸디 홈 " + sgn(L) + " · 핸디승 확률(몫 제외) " + pct(fh[0], 0)) + bars(rr) + say(rr) + table(["핸디승", "핸디패"], rows2));
    }
    var lx = num(v.ol), fo = fair([num(v.o), num(v.u)]);
    if (!(lx > 0) || !fo) return need("베트맨 언더오버 기준점과 오버·언더 배당을 넣으세요.");
    var tot = B.tot, R = B.r, n = tot.reduce(function (a, b) { return a + b; }, 0);
    if (!n) return need("합계 기록이 없습니다.");
    // 총점 = 해외 기준점 + δ + e (e: 실제 총점 − 마감 기준점 분포). 해외 오버 확률에 맞게 δ 를 정한다
    var q = function (p) { var acc = 0; for (var i = 0; i < tot.length; i++) { acc += tot[i]; if (acc >= p * n) return i / 2 - R; } return R; };
    var qq = q(Math.min(0.99, Math.max(0.01, 1 - fo[0])));
    var ev = function (i) { return i / 2 - R; };
    var overAt = function (x) { return rate(tot, ev, -(x - lx + qq)); };
    var rows = lineSet(lx, st.sport === "basketball" ? 2 : 0.5, 4).map(function (x) { var p = overAt(x); return { line: x, v: [p, 1 - p], hl: near(x, lx) }; });
    var po = overAt(lx), ro = [{ k: "오버", real: po, imp: fo[0] }, { k: "언더", real: 1 - po, imp: fo[1] }];
    return out(head(B.tn || n, LABEL[st.sport] + " · 베트맨 " + lx + " 오버 확률(몫 제외) " + pct(fo[0], 0)) + bars(ro) + say(ro) + table(["오버", "언더"], rows));
  }

  /* ───── 조작 ───── */
  function press(attr, val) { $$("[" + attr + "]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute(attr) === val)); }); }
  $$("[data-xo-sport]").forEach(function (b) {
    b.addEventListener("click", function () { st.sport = b.dataset.xoSport; st.grp = (LGS[st.sport] || [["x"]])[0][0]; press("data-xo-sport", st.sport); $("[data-xo-match]").value = ""; drawLgs(); drawInputs(); calc(); });
  });
  $$("[data-xo-mk]").forEach(function (b) {
    b.addEventListener("click", function () { st.mk = b.dataset.xoMk; press("data-xo-mk", st.mk); drawInputs(); calc(); });
  });

  function two(p) { return p > 0 && p < 1 ? [(1 / p).toFixed(2), (1 / (1 - p)).toFixed(2)] : null; }
  function loadToday(list, blist) {
    var sel = $("[data-xo-match]");
    var all = (list || []).map(function (g) { return { g: g, b: false }; }).concat((blist || []).map(function (g) { return { g: g, b: true }; }));
    all.sort(function (a, b) { return String(a.g.ko) < String(b.g.ko) ? -1 : 1; });
    if (!all.length) return;
    all.forEach(function (it, i) {
      var g = it.g, o = document.createElement("option"), ko = String(g.ko);
      o.value = String(i);
      o.textContent = (+ko.slice(5, 7)) + "/" + (+ko.slice(8, 10)) + " " + ko.slice(11, 16) + " · " + g.label + " (" + g.league + ")";
      sel.appendChild(o);
    });
    $("[data-xo-load]").hidden = false;
    sel.addEventListener("change", function () {
      var it = all[+sel.value];
      if (!it) return;
      var g = it.g;
      st.sport = g.sport; press("data-xo-sport", st.sport);
      if (it.b) {
        st.grp = g.grp;
        var b = V[st.sport + "_b"], m = g.bm || {};
        if (m.WL) { b.h = String(m.WL.H || ""); b.a = String(m.WL.A || ""); b.d = m.WL.D ? String(m.WL.D) : ""; }
        if (m.HANDICAP) { b.hl = String(m.HANDICAP.line); b.ho = String(m.HANDICAP.H || ""); b.ao = String(m.HANDICAP.A || ""); b.hd = m.HANDICAP.D ? String(m.HANDICAP.D) : ""; }
        if (m.OU) { b.ol = String(m.OU.line); b.o = String(m.OU.O || ""); b.u = String(m.OU.U || ""); }
      } else {
        st.grp = "x";
        var v = V[st.sport], m2 = g.bm || {};
        if (m2.WL) { v.h = String(m2.WL.H || ""); v.a = String(m2.WL.A || ""); v.d = m2.WL.D ? String(m2.WL.D) : ""; }
        if (m2.HANDICAP) { v.hl = String(m2.HANDICAP.line); v.ho = String(m2.HANDICAP.H || ""); v.ao = String(m2.HANDICAP.A || ""); v.hd = m2.HANDICAP.D ? String(m2.HANDICAP.D) : ""; }
        if (m2.OU) { v.ol = String(m2.OU.line); v.o = String(m2.OU.O || ""); v.u = String(m2.OU.U || ""); }
      }
      drawLgs(); drawInputs(); calc();
    });
  }

  drawLgs();
  drawInputs();
  fetch("/data/xbook.json", { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) { D = d || {}; drawLgs(); loadToday(D.today, D.btoday); calc(); })
    .catch(function () { D = {}; need("기록을 불러오지 못했습니다. 새로고침해 보세요."); });
})();
