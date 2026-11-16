/* 배당 분석 계산기: 해외 배당 → 해외 배당이 비슷했던 과거 경기의 실제 결과.
   승패(승무패)·핸디캡·언더오버 모두 해외 기준점·해외 배당으로 넣고 본다. 베트맨 배당·베트맨 기록은 쓰지 않는다.
   데이터(/data/xbook.json)는 엔진의 xbook.py 와 같은 구간·같은 방식으로 센다. */
(function () {
  "use strict";
  var root = document.querySelector("[data-xo]");
  if (!root) return;
  var $ = function (s, r) { return (r || root).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || root).querySelectorAll(s)); };
  var NEED = 250;
  var D = null;
  var st = { sport: "soccer", mk: "main" };
  var DEF = {
    soccer: { h: "2.10", d: "3.30", a: "3.40", hl: "-0.5", ho: "1.95", ao: "1.95", ol: "2.5", o: "1.90", u: "1.90" },
    basketball: { h: "1.60", a: "2.35", hl: "-5.5", ho: "1.91", ao: "1.91", ol: "220.5", o: "1.91", u: "1.91" },
    baseball: { h: "1.75", a: "2.10", hl: "-1.5", ho: "2.10", ao: "1.75", ol: "8.5", o: "1.91", u: "1.91" }
  };
  var V = JSON.parse(JSON.stringify(DEF));
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
  var FIELDS = {
    soccer: { main: [["h", "홈"], ["d", "무"], ["a", "원정"]],
      hcp: [["hl", "해외 핸디 (홈)"], ["ho", "홈 배당"], ["ao", "원정 배당"]],
      ou: [["ol", "해외 기준점"], ["o", "오버 배당"], ["u", "언더 배당"]] },
    us: { main: [["h", "홈"], ["a", "원정"]],
      hcp: [["hl", "해외 핸디 (홈)"], ["ho", "홈 배당"], ["ao", "원정 배당"]],
      ou: [["ol", "해외 기준점"], ["o", "오버 배당"], ["u", "언더 배당"]] }
  };
  function fields() { return (st.sport === "soccer" ? FIELDS.soccer : FIELDS.us)[st.mk]; }
  function drawInputs() {
    var box = $("[data-xo-inputs]");
    box.innerHTML = "";
    fields().forEach(function (f) {
      var lab = document.createElement("label"), sp = document.createElement("span"), inp = document.createElement("input");
      sp.textContent = f[1];
      inp.className = "input"; inp.type = "text"; inp.inputMode = "decimal"; inp.autocomplete = "off";
      inp.value = V[st.sport][f[0]] || ""; inp.dataset.k = f[0];
      inp.setAttribute("aria-label", f[1]);
      inp.addEventListener("input", function () { V[st.sport][f[0]] = inp.value; calc(); });
      lab.appendChild(sp); lab.appendChild(inp); box.appendChild(lab);
    });
    box.style.setProperty("--cols", fields().length);
    $("[data-xo-main]").textContent = st.sport === "soccer" ? "승무패" : "승패";
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
  var SUBJ = { "홈승": "홈승이", "무": "무승부가", "원정승": "원정승이", "홈": "홈이", "원정": "원정이", "오버": "오버가", "언더": "언더가" };
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
        return "<tr" + (r.hl ? ' class="is-hl"' : "") + "><td>" + r.line + (r.hl ? ' <small class="xo-tag">해외 기준점</small>' : "") + "</td>" + r.v.map(function (v) {
          return '<td class="n"><span class="xo-cell' + (v === best ? " is-top" : "") + '"><i style="width:' + (v * 100).toFixed(1) + '%"></i><b>' + pct(v) + "</b></span></td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }
  function need(msg) { out('<p class="none">' + msg + "</p>"); }
  function lineSet(center, step, k) { var o = []; for (var i = -k; i <= k; i++) o.push(Math.round((center + i * step) * 4) / 4); return o; }

  function calc() {
    if (!D) return;
    return st.sport === "soccer" ? calcSoccer(V.soccer) : calcUS(V[st.sport]);
  }

  function calcSoccer(v) {
    var S = D.soc;
    if (!S) return need("축구 기록을 모으는 중입니다.");
    if (st.mk === "main") {
      var f = fair([num(v.h), num(v.d), num(v.a)]);
      if (!f) return need("해외 승무패 배당(홈·무·원정)을 1보다 큰 숫자로 넣으세요.");
      var bi = bin(f[0], S.w), bj = bin(f[2], S.w);
      var acc = gather(S.pair, function (r) { var o = []; for (var a = -r; a <= r; a++) for (var b = -r; b <= r; b++) o.push((bi + a) + "|" + (bj + b)); return o; });
      if (!acc) return need("이 배당 구도는 과거 기록이 부족합니다.");
      var n = acc[0], rows = [{ k: "홈승", real: acc[1] / n, imp: f[0] }, { k: "무", real: acc[2] / n, imp: f[1] }, { k: "원정승", real: acc[3] / n, imp: f[2] }];
      return out(head(n, "유럽 축구 · 해외 승무패 확률 " + pct(f[0], 0) + "·" + pct(f[1], 0) + "·" + pct(f[2], 0)) + bars(rows) + say(rows));
    }
    var M = S.dm;
    if (st.mk === "hcp") {
      var L = num(v.hl), fh = fair([num(v.ho), num(v.ao)]);
      if (!isFinite(L) || !fh) return need("해외 핸디 기준점(홈 기준, 예: -0.5)과 홈·원정 배당을 넣으세요.");
      var cells = Object.keys(S.pair).map(function (k) { var r = S.pair[k]; return { row: [r[4]].concat(r.slice(5)) }; }).filter(function (c) { return c.row[0] >= 40; });
      if (!cells.length) return need("축구 핸디캡은 득점 차 기록을 받는 중입니다. 자동 업데이트로 하루 안에 채워집니다.");
      var dv = function (i) { return i - M; };
      var hist = similar(cells, function (c) { return rate(c.row.slice(1), dv, L); }, fh[0]);
      if (!hist) return need("이 핸디 구도는 과거 기록이 부족합니다.");
      var hd = hist.slice(1), rows2 = lineSet(L, 1, 2).map(function (x) { var p = rate(hd, dv, x); return { line: "홈 " + sgn(x), v: [p, 1 - p], hl: near(x, L) }; });
      var pr = rate(hd, dv, L), rr = [{ k: "홈", real: pr, imp: fh[0] }, { k: "원정", real: 1 - pr, imp: fh[1] }];
      return out(head(hist[0], "유럽 축구 · 해외 핸디 홈 " + sgn(L) + " 홈 확률 " + pct(fh[0], 0)) + bars(rr) + say(rr) + table(["홈", "원정"], rows2));
    }
    var OL = num(v.ol), fo = fair([num(v.o), num(v.u)]);
    if (!(OL > 0) || !fo) return need("해외 언더오버 기준점(예: 2.5)과 오버·언더 배당을 넣으세요.");
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
    return out(head(gh[0], "유럽 축구 · 해외 " + OL + " 오버 확률 " + pct(fo[0], 0) + " · 평균 " + (avg / gh[0]).toFixed(2) + "골") + bars(ro) + say(ro) + table(["오버", "언더"], rows3));
  }

  function calcUS(v) {
    var B = D[st.sport];
    if (!B) return need(LABEL[st.sport] + " 기록을 모으는 중입니다.");
    var M = B.m, mv = function (i) { return i - M; };
    if (st.mk === "main") {
      var f = fair([num(v.h), num(v.a)]);
      if (!f) return need("해외 승패 배당(홈·원정)을 1보다 큰 숫자로 넣으세요.");
      var i0 = bin(f[0], B.w), h = gather(B.wl, function (r) { return ring(i0, r); });
      if (!h) return need("이 배당 구도는 과거 기록이 부족합니다.");
      var pw = rate(h.slice(1), mv, 0), rws = [{ k: "홈승", real: pw, imp: f[0] }, { k: "원정승", real: 1 - pw, imp: f[1] }];
      return out(head(h[0], LABEL[st.sport] + " · 해외 승패 확률 " + pct(f[0], 0) + " 대 " + pct(f[1], 0)) + bars(rws) + say(rws));
    }
    if (st.mk === "hcp") {
      var L = num(v.hl), fh = fair([num(v.ho), num(v.ao)]);
      if (!isFinite(L) || !fh) return need("해외 핸디 기준점(홈 기준, 예: -5.5)과 홈·원정 배당을 넣으세요.");
      var cells = Object.keys(B.wl).map(function (k) { return { row: B.wl[k] }; }).filter(function (c) { return c.row[0] >= 40; });
      var hist = similar(cells, function (c) { return rate(c.row.slice(1), mv, L); }, fh[0]);
      if (!hist) return need("이 핸디 구도는 과거 기록이 부족합니다.");
      var hd = hist.slice(1), step = st.sport === "basketball" ? 2 : 1, k = st.sport === "basketball" ? 4 : 2;
      var rows2 = lineSet(L, step, k).map(function (x) { var p = rate(hd, mv, x); return { line: "홈 " + sgn(x), v: [p, 1 - p], hl: near(x, L) }; });
      var pr = rate(hd, mv, L), rr = [{ k: "홈", real: pr, imp: fh[0] }, { k: "원정", real: 1 - pr, imp: fh[1] }];
      return out(head(hist[0], LABEL[st.sport] + " · 해외 핸디 홈 " + sgn(L) + " 홈 확률 " + pct(fh[0], 0)) + bars(rr) + say(rr) + table(["홈", "원정"], rows2));
    }
    var lx = num(v.ol), fo = fair([num(v.o), num(v.u)]);
    if (!(lx > 0) || !fo) return need("해외 언더오버 기준점과 오버·언더 배당을 넣으세요.");
    var tot = B.tot, R = B.r, n = tot.reduce(function (a, b) { return a + b; }, 0);
    if (!n) return need("합계 기록이 없습니다.");
    // 총점 = 해외 기준점 + δ + e (e: 실제 총점 − 마감 기준점 분포). 해외 오버 확률에 맞게 δ 를 정한다
    var q = function (p) { var acc = 0; for (var i = 0; i < tot.length; i++) { acc += tot[i]; if (acc >= p * n) return i / 2 - R; } return R; };
    var qq = q(Math.min(0.99, Math.max(0.01, 1 - fo[0])));
    var ev = function (i) { return i / 2 - R; };
    var overAt = function (x) { return rate(tot, ev, -(x - lx + qq)); };
    var rows = lineSet(lx, st.sport === "basketball" ? 2 : 0.5, 4).map(function (x) { var p = overAt(x); return { line: x, v: [p, 1 - p], hl: near(x, lx) }; });
    var po = overAt(lx), ro = [{ k: "오버", real: po, imp: fo[0] }, { k: "언더", real: 1 - po, imp: fo[1] }];
    return out(head(B.tn || n, LABEL[st.sport] + " · 해외 " + lx + " 오버 확률 " + pct(fo[0], 0)) + bars(ro) + say(ro) + table(["오버", "언더"], rows));
  }

  /* ───── 조작 ───── */
  function press(attr, val) { $$("[" + attr + "]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute(attr) === val)); }); }
  $$("[data-xo-sport]").forEach(function (b) {
    b.addEventListener("click", function () { st.sport = b.dataset.xoSport; press("data-xo-sport", st.sport); $("[data-xo-match]").value = ""; drawInputs(); calc(); });
  });
  $$("[data-xo-mk]").forEach(function (b) {
    b.addEventListener("click", function () { st.mk = b.dataset.xoMk; press("data-xo-mk", st.mk); drawInputs(); calc(); });
  });

  function two(p) { return p > 0 && p < 1 ? [(1 / p).toFixed(2), (1 / (1 - p)).toFixed(2)] : null; }
  function loadToday(list) {
    var sel = $("[data-xo-match]");
    if (!list || !list.length) return;
    list.forEach(function (g, i) {
      var o = document.createElement("option"), ko = String(g.ko);
      o.value = String(i);
      o.textContent = (+ko.slice(5, 7)) + "/" + (+ko.slice(8, 10)) + " " + ko.slice(11, 16) + " · " + g.label + " (" + g.league + ")";
      sel.appendChild(o);
    });
    $("[data-xo-load]").hidden = false;
    sel.addEventListener("change", function () {
      var g = list[+sel.value];
      if (!g) return;
      st.sport = g.sport; press("data-xo-sport", st.sport);
      var v = V[st.sport], h = g.h2h || {};
      if (h.H) v.h = String(h.H);
      if (h.A) v.a = String(h.A);
      if (h.D) v.d = String(h.D);
      var sp = g.spread && two(g.spread[1]);
      if (sp) { v.hl = String(g.spread[0]); v.ho = sp[0]; v.ao = sp[1]; }
      var tt = g.total && two(g.total[1]);
      if (tt) { v.ol = String(g.total[0]); v.o = tt[0]; v.u = tt[1]; }
      drawInputs(); calc();
    });
  }

  drawInputs();
  fetch("/data/xbook.json", { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) { D = d || {}; loadToday(D.today); calc(); })
    .catch(function () { D = {}; need("기록을 불러오지 못했습니다. 새로고침해 보세요."); });
})();
