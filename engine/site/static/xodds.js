/* 배당 분석 계산기: 해외 배당 → 비슷했던 과거 경기의 실제 결과.
   데이터(/data/xbook.json)는 엔진의 xbook.py 와 같은 구간·같은 방식으로 센다. 베트맨 기록은 쓰지 않는다. */
(function () {
  "use strict";
  var root = document.querySelector("[data-xo]");
  if (!root) return;
  var $ = function (s, r) { return (r || root).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || root).querySelectorAll(s)); };
  var NEED = 250;
  var D = null;
  var st = { sport: "soccer", mk: "main", hl: null };
  var DEF = {
    soccer: { h: "2.10", d: "3.30", a: "3.40", o: "1.90", u: "1.90" },
    basketball: { h: "1.60", a: "2.35", line: "220.5", o: "1.91", u: "1.91" },
    baseball: { h: "1.75", a: "2.10", line: "8.5", o: "1.91", u: "1.91" }
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
  function gather(t, keysAt) {
    var acc = null;
    for (var r = 0; r <= 3; r++) {
      acc = null;
      keysAt(r).forEach(function (k) {
        var row = t[k];
        if (!row) return;
        acc = acc ? acc.map(function (x, i) { return x + row[i]; }) : row.slice();
      });
      if (acc && acc[0] >= NEED) return acc;
    }
    return acc && acc[0] >= NEED / 3 ? acc : null;
  }
  function ring(i, r) { var o = []; for (var a = -r; a <= r; a++) o.push(String(i + a)); return o; }
  function sgn(x) { return (x > 0 ? "+" : "") + x; }

  /* ───── 입력칸 ───── */
  var FIELDS = {
    soccer: { main: [["h", "홈"], ["d", "무"], ["a", "원정"]], hcp: [["h", "홈"], ["d", "무"], ["a", "원정"]], ou: [["o", "오버 2.5"], ["u", "언더 2.5"]] },
    us: { main: [["h", "홈"], ["a", "원정"]], hcp: [["h", "홈 (승패 배당)"], ["a", "원정 (승패 배당)"]], ou: [["line", "해외 기준점"], ["o", "오버"], ["u", "언더"]] }
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
      inp.setAttribute("aria-label", f[1] + (f[0] === "line" ? "" : " 배당"));
      inp.addEventListener("input", function () { V[st.sport][f[0]] = inp.value; st.hl = st.hl && st.hl.keep ? st.hl : null; calc(); });
      lab.appendChild(sp); lab.appendChild(inp); box.appendChild(lab);
    });
    box.style.setProperty("--cols", fields().length);
    $("[data-xo-main]").textContent = st.sport === "soccer" ? "승무패" : "승패";
  }

  /* ───── 결과 그리기 ───── */
  function out(html) { $("[data-xo-out]").innerHTML = html; }
  function head(n, sub) {
    return '<div class="xo-head"><b>비슷한 경기 ' + fmtN(n) + '개</b><span>' + sub + "</span></div>";
  }
  function bars(rows) {
    return '<ul class="xo-bars">' + rows.map(function (r) {
      var d = (r.real - r.imp) * 100, cls = Math.abs(d) < 1 ? "flat" : d > 0 ? "up" : "down";
      return '<li><span class="xo-k">' + r.k + '</span><span class="xo-bar"><i style="width:' + (r.real * 100).toFixed(1) + '%"></i></span><b>' + pct(r.real) +
        '</b><small>배당 확률 ' + pct(r.imp) + ' · <em class="' + cls + '">' + (d >= 0 ? "+" : "") + d.toFixed(1) + "%p</em></small></li>";
    }).join("") + "</ul>";
  }
  function say(rows) {
    var big = rows.slice().sort(function (a, b) { return Math.abs(b.real - b.imp) - Math.abs(a.real - a.imp); })[0];
    var d = (big.real - big.imp) * 100;
    if (Math.abs(d) < 1) return '<p class="xo-say">배당이 말한 확률과 실제 결과가 거의 같았습니다(차이 1%p 미만). 이 구도에서는 배당을 그대로 믿어도 됩니다.</p>';
    var SUBJ = { "홈승": "홈승이", "무": "무승부가", "원정승": "원정승이" };
    return '<p class="xo-say">' + (SUBJ[big.k] || big.k) + " 배당이 말한 것보다 <b>" + Math.abs(d).toFixed(1) + "%p " + (d > 0 ? "더 자주" : "덜") + "</b> 나왔습니다." +
      (Math.abs(d) >= 3 ? " 차이가 큰 편입니다." : "") + "</p>";
  }
  function table(cols, rows) {
    return '<div class="tblw"><table class="tbl xo-tbl"><thead><tr><th>기준점</th>' + cols.map(function (c) { return '<th class="n">' + c + "</th>"; }).join("") +
      "</tr></thead><tbody>" + rows.map(function (r) {
        var best = Math.max.apply(null, r.v);
        return "<tr" + (r.hl ? ' class="is-hl"' : "") + "><td>" + r.line + (r.hl ? ' <small class="xo-tag">베트맨 기준점</small>' : "") + "</td>" + r.v.map(function (v) {
          return '<td class="n"><span class="xo-cell' + (v === best ? " is-top" : "") + '"><i style="width:' + (v * 100).toFixed(1) + '%"></i><b>' + pct(v) + "</b></span></td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }
  function isHl(kind, line) {
    return !!(st.hl && st.hl[kind] && st.hl[kind].some(function (x) { return Math.abs(x - line) < 1e-9; }));
  }
  function need(msg) { out('<p class="none">' + msg + "</p>"); }

  function calc() {
    if (!D) return;
    var v = V[st.sport];
    if (st.sport === "soccer") return calcSoccer(v);
    return calcUS(v);
  }

  function calcSoccer(v) {
    var S = D.soc;
    if (!S) return need("축구 기록을 모으는 중입니다.");
    if (st.mk === "ou") {
      var fo = fair([num(v.o), num(v.u)]);
      if (!fo) return need("오버·언더 2.5 배당을 1보다 큰 숫자로 넣으세요.");
      var i = bin(fo[0], S.gw), h = gather(S.goals, function (r) { return ring(i, r); });
      if (!h) return need("이 배당 구도는 과거 기록이 부족합니다.");
      var n = h[0], avg = 0;
      for (var g = 0; g < h.length - 1; g++) avg += g * h[1 + g];
      var rows = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5].map(function (L) {
        var over = 0;
        for (var g2 = 0; g2 < h.length - 1; g2++) if (g2 > L) over += h[1 + g2];
        return { line: L, v: [over / n, 1 - over / n], hl: isHl("ou", L) };
      });
      return out(head(n, "유럽 축구 · 오버 2.5 확률 " + pct(fo[0], 0) + " 구간 · 평균 " + (avg / n).toFixed(2) + "골") + table(["오버", "언더"], rows) +
        '<p class="xo-say">2.5 기준 실제 오버 ' + pct(rows[2].v[0]) + ", 배당 확률 " + pct(fo[0]) + ". 다른 기준점은 같은 경기들의 실제 총 득점으로 셉니다.</p>");
    }
    var f = fair([num(v.h), num(v.d), num(v.a)]);
    if (!f) return need("홈·무·원정 배당을 1보다 큰 숫자로 넣으세요.");
    var bi = bin(f[0], S.w), bj = bin(f[2], S.w);
    var acc = gather(S.pair, function (r) { var o = []; for (var a = -r; a <= r; a++) for (var b = -r; b <= r; b++) o.push((bi + a) + "|" + (bj + b)); return o; });
    if (!acc) return need("이 배당 구도는 과거 기록이 부족합니다.");
    var n2 = acc[0], sub = "유럽 축구 · 해외 확률 " + pct(f[0], 0) + "·" + pct(f[1], 0) + "·" + pct(f[2], 0);
    if (st.mk === "main") {
      var rws = [{ k: "홈승", real: acc[1] / n2, imp: f[0] }, { k: "무", real: acc[2] / n2, imp: f[1] }, { k: "원정승", real: acc[3] / n2, imp: f[2] }];
      return out(head(n2, sub) + bars(rws) + say(rws));
    }
    var dn = acc[4], diff = acc.slice(5), M = S.dm;
    if (dn < 100) return need("축구 핸디캡은 득점 차 기록을 받는 중입니다. 자동 업데이트로 하루 안에 채워집니다.");
    var lines = [-2, -1, 1, 2].concat((st.hl && st.hl.hcp) || []).filter(function (x, i, a) { return a.indexOf(x) === i; }).sort(function (a, b) { return a - b; });
    var rows2 = lines.map(function (L) {
      var o = [0, 0, 0];
      diff.forEach(function (c, idx) { var x = idx - M + L; o[x > 0 ? 0 : x === 0 ? 1 : 2] += c; });
      return { line: "홈 " + sgn(L), v: [o[0] / dn, o[1] / dn, o[2] / dn], hl: isHl("hcp", L) };
    });
    return out(head(dn, sub) + table(["홈", "무", "원정"], rows2) + '<p class="xo-say">홈 득점에 기준점을 더해 원정 득점과 비교합니다. 같은 경기들의 실제 득점 차로 셉니다.</p>');
  }

  function calcUS(v) {
    var B = D[st.sport];
    if (!B) return need(LABEL[st.sport] + " 기록을 모으는 중입니다.");
    var M = B.m;
    if (st.mk === "ou") {
      var lx = num(v.line), fo = fair([num(v.o), num(v.u)]);
      if (!(lx > 0) || !fo) return need("해외 기준점과 오버·언더 배당을 넣으세요.");
      var tot = B.tot, R = B.r, n = tot.reduce(function (a, b) { return a + b; }, 0);
      if (!n) return need("합계 기록이 없습니다.");
      var q = function (p) { var acc = 0; for (var i = 0; i < tot.length; i++) { acc += tot[i]; if (acc >= p * n) return i / 2 - R; } return R; };
      var qq = q(Math.min(0.99, Math.max(0.01, 1 - fo[0])));
      var step = st.sport === "basketball" ? 2 : 0.5, half = 4;
      var base = Math.round(lx * 2) / 2;
      var lines = [];
      for (var d = -half; d <= half; d++) lines.push(base + d * step);
      ((st.hl && st.hl.ou) || []).forEach(function (L) { if (lines.indexOf(L) < 0) lines.push(L); });
      lines.sort(function (a, b) { return a - b; });
      var rows = lines.map(function (L) {
        var cut = L - lx + qq, over = 0, push = 0;
        tot.forEach(function (c, i) { var e = i / 2 - R; if (e > cut) over += c; else if (e === cut) push += c; });
        var p = n - push ? over / (n - push) : 0.5;
        return { line: L, v: [p, 1 - p], hl: isHl("ou", L) };
      });
      return out(head(B.tn || n, LABEL[st.sport] + " · 해외 " + lx + " 오버 확률 " + pct(fo[0], 0)) + table(["오버", "언더"], rows) +
        '<p class="xo-say">해외 기준점과 다른 기준점에서의 결과입니다. 실제 총점이 마감 기준점에서 얼마나 벗어났는지의 분포로 셉니다.</p>');
    }
    var f = fair([num(v.h), num(v.a)]);
    if (!f) return need("홈·원정 배당을 1보다 큰 숫자로 넣으세요.");
    var i0 = bin(f[0], B.w), h = gather(B.wl, function (r) { return ring(i0, r); });
    if (!h) return need("이 배당 구도는 과거 기록이 부족합니다.");
    var n2 = h[0], margins = h.slice(1), sub = LABEL[st.sport] + " · 해외 확률 " + pct(f[0], 0) + " 대 " + pct(f[1], 0);
    function cover(L) {
      var w = 0, p = 0;
      margins.forEach(function (c, idx) { var x = idx - M + L; if (x > 0) w += c; else if (x === 0) p += c; });
      return n2 - p ? w / (n2 - p) : 0.5;
    }
    if (st.mk === "main") {
      var pw = cover(0), rws = [{ k: "홈승", real: pw, imp: f[0] }, { k: "원정승", real: 1 - pw, imp: f[1] }];
      return out(head(n2, sub) + bars(rws) + say(rws));
    }
    var lines2;
    if (st.sport === "basketball") {
      var acc = 0, med = 0;
      for (var k = 0; k < margins.length; k++) { acc += margins[k]; if (acc >= n2 / 2) { med = k - M; break; } }
      var b0 = -Math.round(med) - 0.5;
      lines2 = [];
      for (var d2 = -4; d2 <= 4; d2++) lines2.push(b0 + d2 * 2);
    } else lines2 = [-2.5, -1.5, 1.5, 2.5];
    ((st.hl && st.hl.hcp) || []).forEach(function (L) { if (lines2.indexOf(L) < 0) lines2.push(L); });
    lines2.sort(function (a, b) { return a - b; });
    var rows2 = lines2.map(function (L) { var p = cover(L); return { line: "홈 " + sgn(L), v: [p, 1 - p], hl: isHl("hcp", L) }; });
    return out(head(n2, sub) + table(["홈", "원정"], rows2) + '<p class="xo-say">홈 점수에 기준점을 더해 원정 점수와 비교합니다. 같은 경기들의 실제 점수 차로 셉니다.</p>');
  }

  /* ───── 조작 ───── */
  function press(attr, val) { $$("[" + attr + "]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute(attr) === val)); }); }
  $$("[data-xo-sport]").forEach(function (b) {
    b.addEventListener("click", function () { st.sport = b.dataset.xoSport; st.hl = null; press("data-xo-sport", st.sport); $("[data-xo-match]").value = ""; drawInputs(); calc(); });
  });
  $$("[data-xo-mk]").forEach(function (b) {
    b.addEventListener("click", function () { st.mk = b.dataset.xoMk; press("data-xo-mk", st.mk); drawInputs(); calc(); });
  });

  function loadToday(list) {
    var sel = $("[data-xo-match]");
    if (!list || !list.length) return;
    list.forEach(function (g, i) {
      var o = document.createElement("option");
      // 킥오프는 한국 시각 문자열(2026-11-17T09:00:00+09:00) 그대로 쓴다(보는 사람의 시간대와 무관하게 사이트 전체와 같은 시각)
      var ko = String(g.ko);
      o.value = String(i);
      o.textContent = (+ko.slice(5, 7)) + "/" + (+ko.slice(8, 10)) + " " + ko.slice(11, 16) + " · " + g.label + " (" + g.league + ")";
      sel.appendChild(o);
    });
    $("[data-xo-load]").hidden = false;
    sel.addEventListener("change", function () {
      var g = list[+sel.value];
      if (!g) { st.hl = null; calc(); return; }
      st.sport = g.sport; press("data-xo-sport", st.sport);
      var v = V[st.sport], h = g.h2h || {};
      if (h.H) v.h = String(h.H);
      if (h.A) v.a = String(h.A);
      if (h.D) v.d = String(h.D);
      if (g.total && g.total[1] > 0 && g.total[1] < 1) {
        var lx = g.total[0], p = g.total[1];
        if (st.sport !== "soccer") v.line = String(lx);
        if (st.sport !== "soccer" || Math.abs(lx - 2.5) < 1e-9) { v.o = (1 / p).toFixed(2); v.u = (1 / (1 - p)).toFixed(2); }
      }
      st.hl = { hcp: g.hcp || [], ou: g.ou || [], keep: true };
      if (st.mk === "hcp" && !(g.hcp || []).length && (g.ou || []).length) { st.mk = "ou"; press("data-xo-mk", "ou"); }
      drawInputs(); calc();
    });
  }

  drawInputs();
  fetch("/data/xbook.json", { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) { D = d || {}; loadToday(D.today); calc(); })
    .catch(function () { D = {}; need("기록을 불러오지 못했습니다. 새로고침해 보세요."); });
})();
