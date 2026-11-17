/* 스포츠분석.kr — 화면 동작. 외부 라이브러리 없음. */
(function () {
  "use strict";
  window.__app = 1;
  var doc = document, root = doc.documentElement;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (s, el) { return (el || doc).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(s)); };
  var store = {
    get: function (k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  /* 테마 */
  $$("[data-theme-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var cur = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      var next = cur === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      doc.dispatchEvent(new CustomEvent("themechange"));
    });
  });

  /* 모바일 메뉴 */
  var navBtn = $("[data-nav-toggle]"), nav = $("#nav");
  if (navBtn && nav) navBtn.addEventListener("click", function () {
    var open = navBtn.getAttribute("aria-expanded") !== "true";
    navBtn.setAttribute("aria-expanded", String(open));
    nav.classList.toggle("is-open", open);
  });

  /* 숫자 카운트업 */
  function countUp(el) {
    var to = parseFloat(el.dataset.count);
    if (!isFinite(to) || reduce || to === 0) return;
    var t0 = null, dur = 900 + Math.min(600, to * 8);
    el.textContent = "0";
    function step(t) {
      if (!t0) t0 = t;
      var k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(to * e).toLocaleString("ko-KR");
      if (k < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /* 스크롤 등장 */
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("is-in");
        $$("[data-count]", e.target).forEach(countUp);
        io.unobserve(e.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    $$("[data-reveal]").forEach(function (el) { io.observe(el); });
    var heroStats = $(".stat-row");
    if (heroStats) $$("[data-count]", heroStats).forEach(countUp);
  } else {
    $$("[data-reveal]").forEach(function (el) { el.classList.add("is-in"); });
  }

  /* 카드 3D 기울기 + 손가락 위치 빛 */
  function tiltCards(root) {
    if (reduce || !matchMedia("(hover: hover)").matches) return;
    $$(".combo, .top-pick", root).forEach(function (n) {
      n.addEventListener("pointermove", function (e) {
        var r = n.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        n.style.transform = "perspective(900px) rotateX(" + ((0.5 - y) * 6) + "deg) rotateY(" + ((x - 0.5) * 8) + "deg)";
        n.style.setProperty("--mx", (x * 100) + "%"); n.style.setProperty("--my", (y * 100) + "%");
      });
      n.addEventListener("pointerleave", function () { n.style.transform = ""; });
    });
  }
  tiltCards(doc);

  /* 레일: 10초마다 자동으로 다음 카드, 손대면 멈춤. 아래 점·화살표로 몇 장인지와 위치를 보여 준다 */
  $$("[data-rail]").forEach(function (rail) {
    var hold = false, timer;
    var nav = doc.createElement("div"); nav.className = "rail-nav";
    var prev = doc.createElement("button"), dots = doc.createElement("div"), nxt = doc.createElement("button");
    prev.type = nxt.type = "button"; prev.className = "rail-btn"; nxt.className = "rail-btn";
    prev.setAttribute("aria-label", "이전 경기"); nxt.setAttribute("aria-label", "다음 경기");
    prev.innerHTML = "&#8249;"; nxt.innerHTML = "&#8250;"; dots.className = "rail-dots";
    nav.appendChild(prev); nav.appendChild(dots); nav.appendChild(nxt);
    rail.parentNode.insertBefore(nav, rail.nextSibling);
    function cards() { return Array.prototype.slice.call(rail.children); }
    function cur() {
      var c = cards(), mid = rail.scrollLeft + rail.clientWidth / 2, best = 0, bd = 1e9;
      c.forEach(function (el, i) { var d = Math.abs(el.offsetLeft - rail.offsetLeft + el.offsetWidth / 2 - mid); if (d < bd) { bd = d; best = i; } });
      return best;
    }
    function go(i) {
      var c = cards(); if (!c.length) return;
      i = (i + c.length) % c.length;
      var el = c[i];
      rail.scrollTo({ left: el.offsetLeft - rail.offsetLeft - (rail.clientWidth - el.offsetWidth) / 2, behavior: reduce ? "auto" : "smooth" });
    }
    function paint() {
      var c = cards(), i = cur();
      nav.hidden = c.length < 2;
      if (dots.children.length !== c.length) {
        dots.innerHTML = "";
        c.forEach(function (_, k) {
          var d = doc.createElement("button"); d.type = "button"; d.className = "rail-dot";
          d.setAttribute("aria-label", (k + 1) + "번째 경기");
          d.addEventListener("click", function () { go(k); });
          dots.appendChild(d);
        });
      }
      Array.prototype.forEach.call(dots.children, function (d, k) { d.classList.toggle("is-on", k === i); d.setAttribute("aria-current", k === i ? "true" : "false"); });
      var cnt = $("[data-rail-count]"); if (cnt) cnt.textContent = c.length;
    }
    var st;
    rail.addEventListener("scroll", function () { clearTimeout(st); st = setTimeout(paint, 60); }, { passive: true });
    prev.addEventListener("click", function () { go(cur() - 1); });
    nxt.addEventListener("click", function () { go(cur() + 1); });
    paint();
    setInterval(paint, 60000); // 시작한 경기가 빠지면 점 수도 맞춘다
    if (reduce) return;
    function next() { if (hold || doc.hidden || cards().length < 2) return; go(cur() + 1); }
    var inside = false, touching = false, wheelT;
    function sync() {
      var was = hold; hold = inside || touching;
      if (was && !hold) { clearInterval(timer); timer = setInterval(next, 10000); } // 손을 뗀 뒤 10초를 처음부터 다시 센다
    }
    [rail, nav].forEach(function (el) {
      el.addEventListener("mouseenter", function () { inside = true; sync(); });
      el.addEventListener("mouseleave", function () { inside = false; sync(); });
    });
    rail.addEventListener("focusin", function () { inside = true; sync(); });
    rail.addEventListener("focusout", function () { inside = false; sync(); });
    rail.addEventListener("touchstart", function () { touching = true; sync(); }, { passive: true });
    ["touchend", "touchcancel"].forEach(function (ev) {
      rail.addEventListener(ev, function () { clearTimeout(wheelT); wheelT = setTimeout(function () { touching = false; sync(); }, 1500); }, { passive: true });
    });
    rail.addEventListener("pointerdown", function () { touching = true; sync(); });
    timer = setInterval(next, 10000);
  });

  /* 표 필터(배당 분석) */
  $$("[data-filter-table]").forEach(function (tbl) {
    var keys = tbl.dataset.filterTable.split(","), sels = keys.map(function (k) { return $('[data-filter="' + k + '"]'); });
    function run() {
      $$("tbody tr", tbl).forEach(function (tr) {
        tr.hidden = !keys.every(function (k, i) { return !sels[i] || !sels[i].value || tr.dataset[k] === sels[i].value; });
      });
    }
    sels.forEach(function (s) { if (s) s.addEventListener("change", run); });
  });

  /* 탭 */
  $$("[data-tabs]").forEach(function (tabs) {
    var btns = $$("[role=tab]", tabs), ink = $(".tabs-ink", tabs);
    function place(b) {
      if (!ink) return;
      ink.style.left = b.offsetLeft + "px";
      ink.style.width = b.offsetWidth + "px";
    }
    function select(b, focus) {
      btns.forEach(function (x) {
        var on = x === b;
        x.setAttribute("aria-selected", String(on));
        x.tabIndex = on ? 0 : -1;
        var p = doc.getElementById(x.getAttribute("aria-controls"));
        if (p) p.hidden = !on;
      });
      place(b);
      if (focus) b.focus();
    }
    btns.forEach(function (b, i) {
      b.addEventListener("click", function () { select(b); });
      b.addEventListener("keydown", function (e) {
        var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (d) { e.preventDefault(); select(btns[(i + d + btns.length) % btns.length], true); }
      });
    });
    var cur = btns.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0] || btns[0];
    if (cur) { place(cur); window.addEventListener("resize", function () { place(btns.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0]); }); }
  });

  /* 경기 펼치기 */
  $$("[data-expand]").forEach(function (b) {
    b.addEventListener("click", function () {
      var li = b.parentNode, more = $(".match-more", li);
      if (!more) return;
      var open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", String(open));
      more.hidden = !open;
      li.classList.toggle("is-open", open);
      if (open) requestAnimationFrame(function () { li.classList.add("is-open"); });
    });
  });

  /* 날짜·종목 필터 */
  var fDay = null, fSport = "all", fKind = null;
  function applyFilters() {
    var shown = 0;
    $$(".match").forEach(function (m) {
      var kinds = " " + (m.dataset.kinds || "") + " ";
      m.hidden = !((fSport === "all" || m.dataset.sport === fSport) && (!fDay || m.dataset.day === fDay) && (!fKind || kinds.indexOf(" " + fKind + " ") >= 0));
      if (!m.hidden) shown++;
    });
    // 버튼 숫자: 다른 조건을 그대로 둔 채 그 버튼을 눌렀을 때 남는 경기 수
    var all = $$("li.match"), has = function (li, k) { return (" " + (li.dataset.kinds || "") + " ").indexOf(" " + k + " ") >= 0; };
    var dayOk = function (li) { return !fDay || li.dataset.day === fDay; };
    $$("[data-filters] .chip[data-f]").forEach(function (c) {
      var f = c.dataset.f, sm = $("small", c); if (!sm) return;
      sm.textContent = all.filter(function (li) { return dayOk(li) && (f === "all" || li.dataset.sport === f) && (!fKind || has(li, fKind)); }).length;
    });
    $$("[data-filters] .chip[data-k]").forEach(function (c) {
      var n = all.filter(function (li) { return dayOk(li) && (fSport === "all" || li.dataset.sport === fSport) && has(li, c.dataset.k); }).length;
      var sm = $("small", c); if (sm) sm.textContent = n;
      c.hidden = n === 0 && c.getAttribute("aria-pressed") !== "true";
    });
    // 리그 묶음: 보이는 경기 수, 다 숨으면 묶음도 숨김
    $$("[data-mlg]").forEach(function (g) {
      var n = $$("li.match", g).filter(function (li) { return !li.hidden; }).length;
      g.hidden = n === 0;
      var c = $("[data-mlg-n]", g); if (c) c.textContent = n;
    });
    var em = $("[data-empty]");
    if (em) {
      em.hidden = shown > 0;
      if (!shown) {
        var kl = fKind && $("[data-filters] .chip[data-k=\"" + fKind + "\"]"), sl = fSport !== "all" && $("[data-filters] .chip[data-f=\"" + fSport + "\"]");
        var nm = function (c) { return c ? c.firstChild.textContent.trim() : ""; };
        em.textContent = (sl ? nm(sl) + "에는 " : "") + (kl ? nm(kl) + " 경기가 없습니다." : "조건에 맞는 경기가 없습니다.");
      }
    }
  }
  $$("[data-mlg-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var open = b.getAttribute("aria-expanded") !== "true", body = b.nextElementSibling;
      b.setAttribute("aria-expanded", String(open));
      if (body) body.hidden = !open;
    });
  });
  $$("[data-days]").forEach(function (box) {
    var chips = $$(".chip", box);
    if (chips[0]) fDay = chips[0].dataset.d;
    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        chips.forEach(function (x) { x.setAttribute("aria-pressed", String(x === c)); });
        fDay = c.dataset.d; applyFilters();
      });
    });
  });
  $$("[data-filters]").forEach(function (box) {
    var sp = $$(".chip[data-f]", box), kd = $$(".chip[data-k]", box);
    sp.forEach(function (c) {
      c.addEventListener("click", function () {
        sp.forEach(function (x) { x.setAttribute("aria-pressed", String(x === c)); });
        fSport = c.dataset.f; applyFilters();
      });
    });
    // 역배·핸디·언오버·주의: 누르면 켜고, 다시 누르면 끈다(종목 필터와 함께 적용)
    kd.forEach(function (c) {
      c.addEventListener("click", function () {
        var on = c.getAttribute("aria-pressed") !== "true";
        kd.forEach(function (x) { x.setAttribute("aria-pressed", String(on && x === c)); });
        fKind = on ? c.dataset.k : null; applyFilters();
      });
    });
  });
  applyFilters();

  /* 팀 페이지 최근 경기: 줄을 누르면 점수판(쿼터·이닝·전후반) 펼치기 */
  doc.addEventListener("click", function (e) {
    var tr = e.target.closest && e.target.closest("tr[data-box]");
    if (!tr || e.target.closest("a")) return;
    var row = doc.getElementById(tr.dataset.box);
    if (!row) return;
    row.hidden = !row.hidden;
    tr.setAttribute("aria-expanded", String(!row.hidden));
  });
  doc.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches("tr[data-box]")) { e.preventDefault(); e.target.click(); }
  });

  /* 역배·핸디·언오버: 경기별 묶음, 종류 필터, 처음엔 6경기만, 눌러서 자세히 */
  var linesApply = function () {};
  $$("[data-lines]").forEach(function (sec) {
    var LIMIT = 6, kind = "all", all = false;
    var btn = $("[data-lmore]", sec), cnt = $("[data-lcount]", sec), fchips = $$("[data-lf] .chip", sec);
    var has = function (li, k) { return (" " + li.dataset.kinds + " ").indexOf(" " + k + " ") >= 0; };
    linesApply = function () {
      var items = $$(".lg", sec);
      if (!items.length) { sec.hidden = true; return; }
      fchips.forEach(function (c) {
        var k = c.dataset.k, sm = $("small", c);
        if (k === "all") return;
        var n = items.filter(function (li) { return has(li, k); }).length;
        if (sm) sm.textContent = n;
        c.hidden = n === 0;
        if (n === 0 && kind === k) {
          kind = "all";
          fchips.forEach(function (x) { x.setAttribute("aria-pressed", String(x.dataset.k === "all")); });
        }
      });
      var match = items.filter(function (li) { return kind === "all" || has(li, kind); });
      items.forEach(function (li) { li.hidden = true; });
      match.forEach(function (li, i) { li.hidden = !all && i >= LIMIT; });
      if (cnt) cnt.textContent = items.length;
      if (btn) {
        var rest = match.length - LIMIT;
        btn.hidden = rest <= 0;
        btn.textContent = all ? "접기" : rest + "경기 더 보기";
      }
    };
    fchips.forEach(function (c) {
      c.addEventListener("click", function () {
        fchips.forEach(function (x) { x.setAttribute("aria-pressed", String(x === c)); });
        kind = c.dataset.k; all = false; linesApply();
      });
    });
    if (btn) btn.addEventListener("click", function () {
      all = !all; linesApply();
      if (!all) sec.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $$("[data-lg]", sec).forEach(function (b) {
      b.addEventListener("click", function () {
        var li = b.parentNode, more = $(".lg-more", li), open = b.getAttribute("aria-expanded") !== "true";
        b.setAttribute("aria-expanded", String(open));
        if (more) more.hidden = !open;
        li.classList.toggle("is-open", open);
      });
    });
    linesApply();
  });

  /* 시작한 경기는 시작 시각이 되면 목록·카드·표에서 뺀다(1분마다 확인, 서버 실행 없음).
     오늘 리포트 첫 화면에서만 적용하고, 지난 리포트·경기 페이지는 기록으로 그대로 둔다. */
  if (doc.body.classList.contains("page-report") && $("[data-live]")) {
    var sweep = function () {
      var now = Date.now();
      $$("[data-ko]").forEach(function (el) {
        var t = Date.parse(el.dataset.ko || "");
        if (t && t <= now) el.remove();
      });
      // 비게 된 묶음 정리
      var rail = $("[data-rail]");
      if (rail && !rail.children.length) { var w = rail.closest("section"); if (w) w.remove(); }
      $$(".tab-panel").forEach(function (pn) {
        var grid = $(".combo-grid:not(.nd-grid)", pn);
        if (grid && !grid.children.length) {
          grid.remove();
          if (!$(".none", pn) && !$(".nd-grid", pn)) { var pz = doc.createElement("p"); pz.className = "none"; pz.textContent = "오늘 조합은 모두 시작했습니다. 다음 조합은 오후 7시에 올라옵니다."; pn.appendChild(pz); }
        }
        var tab = doc.getElementById(pn.getAttribute("aria-labelledby") || "");
        var sm = tab && $("small", tab);
        if (sm) sm.textContent = $$(".combo", pn).length;
      });
      $$("table tbody").forEach(function (tb) { if (!tb.children.length) { var sec = tb.closest("section"); if (sec && !sec.closest("#matches")) sec.remove(); } });
      $$(".caution-list").forEach(function (ul) { if (!ul.children.length) { var sec = ul.closest("section"); if (sec) sec.remove(); } });
      var ml = $("#matches"), td = ml && ml.dataset.today;
      var left = $$("#matches li.match").filter(function (li) { return !td || li.dataset.day === td; }).length;
      var rem = $("[data-remain]");
      if (rem) rem.textContent = left;
      var cl = $("[data-combos-left]");
      if (cl) cl.textContent = $$(".combo").length;
      var nx = $("[data-next]"), hero = $(".hero");
      if (nx && hero && (left === 0 || nx.hasAttribute("data-ready")) && hero.nextElementSibling !== nx) {
        hero.parentNode.insertBefore(nx, hero.nextElementSibling);
      }
      var em = $("[data-empty]");
      if (em && left === 0) { em.hidden = false; em.textContent = nx ? "오늘 남은 경기가 없습니다. 위에서 다음 구매일 분석을 확인하세요." : "오늘 남은 경기가 없습니다. 다음 구매일 분석은 오후 7시에 올라옵니다."; }
      linesApply();
      if (typeof applyFilters === "function") applyFilters();
    };
    sweep();
    setInterval(sweep, 60000);
  }

  /* 토스트 */
  var toastEl = $("[data-toast]"), toastT;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add("is-on");
    clearTimeout(toastT);
    toastT = setTimeout(function () { toastEl.classList.remove("is-on"); }, 2200);
  }

  /* ───── 내 조합 ───── */
  var MAX_LEGS = 10, MAX_STAKE = 100000, MAX_SEED = 1000000000, CORR = 0.985;
  var data = null, byId = {};
  var slip = { date: null, ids: [] };

  function loadData() {
    return fetch("/data/today.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        data = d || { legs: [] };
        byId = {};
        data.legs.forEach(function (l) { byId[l.id] = l; });
        var s = store.get("slip");
        if (s && s.date === data.date && Array.isArray(s.ids)) slip = { date: s.date, ids: s.ids.filter(function (id) { return byId[id]; }) };
        else slip = { date: data.date, ids: [] };
        return data;
      })
      .catch(function () { data = { legs: [] }; return data; });
  }
  function legsOf(ids) { return ids.map(function (id) { return byId[id]; }).filter(Boolean); }
  function calc(legs) {
    if (!legs.length) return null;
    var odds = 1, p = 1, pairs = 0, missing = false;
    legs.forEach(function (l, i) {
      odds *= l.odds;
      if (l.p == null) missing = true; else p *= l.p;
      for (var j = i + 1; j < legs.length; j++) {
        var o = legs[j];
        if (o.league === l.league && o.ko && l.ko && o.ko.slice(0, 10) === l.ko.slice(0, 10)) pairs++;
      }
    });
    odds = Math.floor(odds * 100) / 100;
    return { odds: odds, p: missing ? null : p * Math.pow(CORR, pairs) };
  }
  function won(x) { return Math.floor(x).toLocaleString("ko-KR") + "원"; }
  /* 베트맨은 회차가 다른 경기를 한 장에 묶을 수 없다 */
  function mixedRounds(legs) {
    var rs = {};
    legs.forEach(function (l) { if (l.rd) rs[l.rd] = 1; });
    return Object.keys(rs).length > 1;
  }
  var MIXED_MSG = "회차가 다른 경기가 섞여 있습니다. 베트맨에서는 같은 회차 경기끼리만 한 장으로 살 수 있습니다.";
  function pct(x) { return x == null ? "–" : (x * 100).toFixed(x < 0.1 ? 1 : 0) + "%"; }
  /* 켈리 기준 금액. f = (p × 배당 − 1) ÷ (배당 − 1), 그 1/4 만 건다(쿼터 켈리).
     켈리 값이 0 이하(배당이 확률보다 낮게 잡힌 조합)면 적중률 구간별 기본 비율을 쓴다. */
  function stakeFor(p, odds, seed) {
    var kelly = odds > 1 ? (p * odds - 1) / (odds - 1) : 0, f, mode;
    if (kelly > 0) { f = Math.min(0.1, kelly / 4); mode = "kelly"; }
    else { f = p >= 0.6 ? 0.1 : p >= 0.3 ? 0.05 : p >= 0.1 ? 0.03 : p >= 0.03 ? 0.015 : 0.005; mode = "base"; }
    var s = Math.floor(seed * f / 100) * 100;
    return { f: f, kelly: kelly, mode: mode, capped: s > MAX_STAKE, stake: Math.min(MAX_STAKE, Math.max(seed >= 100 ? 100 : 0, s)) };
  }

  function addIds(ids, quiet) {
    if (!data) return;
    var added = 0, replaced = 0, past = 0;
    ids.forEach(function (id) {
      var l = byId[id];
      if (!l) { past++; return; }
      if (slip.ids.indexOf(id) >= 0) return;
      var same = slip.ids.filter(function (x) { return byId[x] && byId[x].match === l.match; });
      if (same.length) { slip.ids = slip.ids.filter(function (x) { return same.indexOf(x) < 0; }); replaced++; }
      if (slip.ids.length >= MAX_LEGS) return;
      slip.ids.push(id); added++;
    });
    save();
    if (!quiet) {
      if (past && !added) toast("지금 발매 중인 경기만 담을 수 있습니다.");
      else if (replaced) toast("같은 경기는 하나만 담깁니다. 선택을 바꿨습니다.");
      else if (added) toast(added + "경기를 담았습니다.");
      else if (slip.ids.length >= MAX_LEGS) toast("최대 10경기까지 묶을 수 있습니다.");
    }
    bump();
  }
  function toggleId(id) {
    var i = slip.ids.indexOf(id);
    if (i >= 0) { slip.ids.splice(i, 1); save(); toast("뺐습니다."); }
    else addIds([id]);
  }
  function save() { slip.date = data && data.date; store.set("slip", slip); render(); }

  var slipEl = $("[data-slip]");
  function bump() {
    var t = $(".slip-tab");
    if (!t || reduce) return;
    t.classList.remove("bump"); void t.offsetWidth; t.classList.add("bump");
  }
  function legLi(l, i) {
    var li = doc.createElement("li");
    li.innerHTML = '<span><small></small><span class="lbl"></span></span><b></b><button type="button" aria-label="빼기">×</button>';
    li.querySelector("small").textContent = (l.no ? l.no + "번 · " : "") + (l.league || "");
    li.querySelector(".lbl").textContent = l.label + " · " + l.pick;
    li.querySelector("b").textContent = l.odds.toFixed(2);
    li.querySelector("button").addEventListener("click", function () { slip.ids.splice(i, 1); save(); });
    return li;
  }
  function render() {
    var legs = legsOf(slip.ids);
    if (slipEl) {
      slipEl.hidden = !(data && data.legs.length);
      $("[data-slip-count]").textContent = legs.length;
      var ol = $("[data-slip-legs]");
      ol.innerHTML = "";
      legs.forEach(function (l, i) { ol.appendChild(legLi(l, i)); });
      var c = calc(legs);
      $("[data-slip-odds]").textContent = c ? c.odds.toFixed(2) : "–";
      $("[data-slip-p]").textContent = c ? pct(c.p) : "–";
      $("[data-slip-pay]").textContent = c ? won(Math.floor(10000 * c.odds / 10) * 10) : "–";
      $("[data-slip-warn]").textContent = mixedRounds(legs) ? MIXED_MSG : "";
    }
    $$(".opick[data-leg]").forEach(function (b) { b.classList.toggle("is-on", slip.ids.indexOf(b.dataset.leg) >= 0); });
    renderTool(legs);
    $$(".tl-game").forEach(function (li) {
      var n = $$(".opick", li).filter(function (b) { return slip.ids.indexOf(b.dataset.leg) >= 0; }).length, h = $(".tl-head", li), c = $(".tl-n", li);
      if (!h || !c) return;
      h.classList.toggle("has-pick", n > 0);
      c.textContent = n ? n + "개 담음" : "마켓 " + $$(".tl-mk", li).length + "개";
    });
  }
  if (slipEl) {
    $("[data-slip-open]").addEventListener("click", function () { slipEl.classList.toggle("is-open"); });
    $("[data-slip-close]").addEventListener("click", function () { slipEl.classList.remove("is-open"); });
    $("[data-slip-clear]").addEventListener("click", function () { slip.ids = []; save(); toast("비웠습니다."); });
    doc.addEventListener("keydown", function (e) { if (e.key === "Escape") slipEl.classList.remove("is-open"); });
  }

  /* ───── 전체 조합 보기(작은 창) ───── */
  var dlg = $("[data-reveal-dialog]"), dlgCard = null, adLoaded = false;
  function comboIds(card) {
    var b = card.querySelector("[data-add-combo]");
    try {
      var ids = JSON.parse(b.dataset.addCombo), outs = JSON.parse(b.dataset.addOutcomes);
      return ids.map(function (id, i) { return id + "|" + outs[i]; });
    } catch (e) { return []; }
  }
  function unmask(card) {
    var full = card.querySelector("template[data-full]"), ol = card.querySelector("[data-legs]");
    if (full && ol && card.querySelector("[data-masked]")) { ol.innerHTML = full.innerHTML; }
    var rb = card.querySelector("[data-reveal-combo]"), ab = card.querySelector(".after-reveal");
    if (rb) rb.hidden = true;
    if (ab) ab.hidden = false;
  }
  var seen = store.get("revealed") || {};
  $$("[data-combo]").forEach(function (card) { if (seen[card.dataset.key]) unmask(card); });
  function openReveal(card) {
    dlgCard = card;
    var full = card.querySelector("template[data-full]");
    $("[data-reveal-legs]", dlg).innerHTML = full ? full.innerHTML : "";
    $("[data-reveal-odds]", dlg).textContent = card.querySelector(".combo-odds").textContent.trim() + " · " + card.querySelector(".combo-size").textContent.trim();
    $("[data-reveal-foot]", dlg).innerHTML = card.querySelector(".combo-foot").innerHTML;
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    if (!adLoaded && dlg.querySelector(".adsbygoogle")) { adLoaded = true; try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {} }
    unmask(card);
    seen[card.dataset.key] = 1; store.set("revealed", seen);
  }
  if (dlg) {
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    $("[data-reveal-add]", dlg).addEventListener("click", function () {
      if (dlgCard) addIds(comboIds(dlgCard));
      dlg.close();
      if (slipEl) slipEl.classList.add("is-open");
    });
  }

  doc.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target : null;
    if (!t) return;
    var b = t.closest(".opick[data-leg]");
    if (b) { e.stopPropagation(); toggleId(b.dataset.leg); return; }
    var rv = t.closest("[data-reveal-combo]");
    if (rv && dlg) { openReveal(rv.closest("[data-combo]")); return; }
    var c = t.closest("[data-add-combo]");
    if (c) {
      addIds(comboIds(c.closest("[data-combo]")));
      if (slipEl && !slipEl.classList.contains("is-open")) slipEl.classList.add("is-open");
    }
  });

  /* ───── 금액 계산기 ───── */
  var tool = $("[data-tool]"), bankEl = $("[data-t-bank]");
  function budget() {
    if (!bankEl) return 0;
    var v = parseInt(String(bankEl.value).replace(/[^0-9]/g, ""), 10) || 0;
    return Math.min(MAX_SEED, v);
  }
  function fmtBudget() {
    if (!bankEl) return;
    var v = budget();
    bankEl.value = v ? v.toLocaleString("ko-KR") : "";
    store.set("budget", v);
  }
  function renderTool(legs) {
    if (!tool) return;
    var ol = $("[data-tool-legs]");
    ol.innerHTML = "";
    legs.forEach(function (l, i) { ol.appendChild(legLi(l, i)); });
    var c = calc(legs), adv = $("[data-t-advice]"), B = budget();
    $("[data-t-odds]").textContent = c ? c.odds.toFixed(2) + "배" : "–";
    $("[data-t-p]").textContent = c ? pct(c.p) : "–";
    if (c && mixedRounds(legs)) {
      $("[data-t-stake]").textContent = "–"; $("[data-t-pay]").textContent = "–";
      adv.textContent = MIXED_MSG + " 한 회차 경기만 남겨 주세요.";
      return;
    }
    if (!c || c.p == null || !B) {
      $("[data-t-stake]").textContent = "–"; $("[data-t-pay]").textContent = "–";
      adv.textContent = !B ? "총 시드를 입력하세요." : !legs.length ? "경기를 고르면 켈리 기준 금액이 나옵니다." : "";
      return;
    }
    var s = stakeFor(c.p, c.odds, B), pay = Math.floor(s.stake * c.odds / 10) * 10;
    $("[data-t-stake]").textContent = won(s.stake);
    $("[data-t-pay]").textContent = won(pay);
    var fp = (s.f * 100).toFixed(s.f < 0.01 ? 2 : 1).replace(/\.?0+$/, "") + "%";
    adv.textContent = "총 시드 " + won(B) + "의 " + fp + (s.capped ? "는 1회 한도를 넘어 " : "인 ") + won(s.stake) + "이 켈리 기준 베팅 금액입니다. 맞을 확률은 " + pct(c.p) +
      "이고, 맞으면 " + won(pay) + "을 받습니다." +
      (s.f > 0 && !s.capped && s.f * B < MAX_STAKE ? " 이 비율이면 시드가 " + won(Math.ceil(MAX_STAKE / s.f / 10000) * 10000) + "을 넘을 때부터 1회 한도 10만 원에 닿습니다." : "") + (legs.length === 1 ? " 한 경기 구매는 베트맨에서 '한경기구매' 표시가 있는 경기만 가능합니다." : "");
  }
  /* 경기 고르기: 경기 하나 = 한 줄. 누르면 승무패·핸디캡·언더오버가 펼쳐진다 */
  var toolOpen = {};
  function renderToolList(q) {
    var ul = $("[data-tool-list]");
    if (!data || !data.legs.length) { ul.innerHTML = '<li class="muted">지금 발매 중인 경기가 없습니다.</li>'; return; }
    var games = {}, order = [];
    data.legs.forEach(function (l) {
      var g = games[l.match];
      if (!g) { g = games[l.match] = { key: l.match, first: l, mks: {}, mkOrder: [] }; order.push(g); }
      var mk = l.mk || "";
      if (!g.mks[mk]) { g.mks[mk] = []; g.mkOrder.push(mk); }
      g.mks[mk].push(l);
    });
    order.sort(function (a, b) { return a.first.ko < b.first.ko ? -1 : a.first.ko > b.first.ko ? 1 : 0; });
    ul.innerHTML = "";
    q = (q || "").trim().toLowerCase();
    order.forEach(function (g) {
      var f = g.first;
      if (q && f.label.toLowerCase().indexOf(q) < 0 && String(f.league).toLowerCase().indexOf(q) < 0) return;
      var li = doc.createElement("li"), head = doc.createElement("button"), body = doc.createElement("div");
      li.className = "tl-game";
      head.type = "button"; head.className = "tl-head";
      head.innerHTML = '<span class="tl-meta"></span><span class="tl-name"></span><span class="tl-n"></span><span class="tl-caret" aria-hidden="true"></span>';
      var ko = String(f.ko || "");
      var tm = $(".tl-meta", head);
      [f.no ? f.no + "번" : "", ko ? (+ko.slice(5, 7)) + "/" + (+ko.slice(8, 10)) + " " + ko.slice(11, 16) : "", f.league].forEach(function (t, i) {
        if (!t) return;
        var sp = doc.createElement("span"); sp.textContent = t; if (i === 2) sp.className = "tl-lg"; tm.appendChild(sp);
      });
      $(".tl-name", head).textContent = f.label;
      var picked = g.mkOrder.reduce(function (n, mk) { return n + g.mks[mk].filter(function (l) { return slip.ids.indexOf(l.id) >= 0; }).length; }, 0);
      $(".tl-n", head).textContent = picked ? picked + "개 담음" : "마켓 " + g.mkOrder.length + "개";
      if (picked) head.classList.add("has-pick");
      var open = !!toolOpen[g.key] || !!q;
      head.setAttribute("aria-expanded", String(open));
      body.className = "tl-body"; body.hidden = !open;
      g.mkOrder.forEach(function (mk) {
        var legs = g.mks[mk], row = doc.createElement("div"), lab = doc.createElement("p"), picks = doc.createElement("div");
        row.className = "tl-mk"; lab.className = "tl-mkl"; lab.textContent = legs[0].mkl || "";
        picks.className = "odds-pick";
        legs.forEach(function (l) {
          var bt = doc.createElement("button");
          bt.type = "button"; bt.className = "opick"; bt.dataset.leg = l.id;
          bt.innerHTML = "<span></span><b></b>";
          bt.querySelector("span").textContent = l.pick;
          bt.querySelector("b").textContent = l.odds.toFixed(2);
          picks.appendChild(bt);
        });
        row.appendChild(lab); row.appendChild(picks); body.appendChild(row);
      });
      head.addEventListener("click", function () {
        var now = head.getAttribute("aria-expanded") !== "true";
        toolOpen[g.key] = now;
        head.setAttribute("aria-expanded", String(now));
        body.hidden = !now;
      });
      li.appendChild(head); li.appendChild(body); ul.appendChild(li);
    });
    if (!ul.children.length) ul.innerHTML = '<li class="muted">검색 결과가 없습니다.</li>';
    render();
  }
  if (tool) {
    var saved = store.get("budget");
    if (saved) bankEl.value = String(saved);
    fmtBudget();
    bankEl.addEventListener("input", function () { fmtBudget(); render(); });
    $$("[data-quick] .chip").forEach(function (c) { c.addEventListener("click", function () { bankEl.value = c.dataset.v; fmtBudget(); render(); }); });
    $("[data-tool-search]").addEventListener("input", function (e) { renderToolList(e.target.value); });
  }

  /* 조합 카드 켈리 기준 금액: 금액 계산기에 넣은 시드(없으면 30만 원) 기준 "시드 30만 원의 1.5% · 켈리 기준 4,500원" */
  function paintStakes() {
    var B = Math.min(MAX_SEED, parseInt(store.get("budget"), 10) || 300000);
    $$("[data-stake]").forEach(function (el) {
      var p = parseFloat(el.dataset.p), o = parseFloat(el.dataset.odds);
      if (!(p > 0) || !(o > 1)) { el.hidden = true; return; }
      var s = stakeFor(p, o, B), fp = (s.f * 100).toFixed(s.f < 0.01 ? 2 : 1).replace(/\.?0+$/, "") + "%";
      el.innerHTML = '<a href="/tool/" title="시드는 금액 계산기에서 바꿀 수 있습니다"></a><b></b>';
      el.querySelector("a").textContent = "시드 " + won(B) + "의 " + fp + (s.capped ? " (1회 한도)" : "");
      el.querySelector("b").textContent = "켈리 기준 " + won(s.stake);
    });
  }
  paintStakes();

  function toneC(t) {
    var m = /([+\-−])\d/.exec(t);
    if (m) return m[1] === "+" ? "#4ade80" : "#ff6b6b";
    if (/오버/.test(t)) return "#4ade80";
    if (/언더/.test(t)) return "#ff6b6b";
    if (/무/.test(t)) return "#fbbf24";
    if (/패/.test(t)) return "#ff6b6b";
    return /승/.test(t) ? "#4ade80" : "#eef0f7";
  }
  /* ───── 내 조합 공유: 링크(받은 사람 화면에 그대로 담김) + 이미지 카드 ───── */
  function shareCode(ids) {
    return ids.map(function (id) {
      var m = /^betman:G101:(\d+):(\d+)\|([A-Z])$/.exec(id);
      return m ? m[1] + "." + m[2] + "." + m[3] : "";
    }).filter(Boolean).join("~");
  }
  function fromCode(s) {
    return String(s || "").split("~").map(function (x) {
      var m = /^(\d{6})\.(\d{1,6})\.([A-Z])$/.exec(x);
      return m ? "betman:G101:" + m[1] + ":" + m[2] + "|" + m[3] : null;
    }).filter(Boolean).slice(0, MAX_LEGS);
  }
  function shareImage(legs, c) {
    return new Promise(function (resolve) {
      try {
        var W = 1080, rowH = 104, H = 330 + legs.length * rowH + 250;
        var cv = doc.createElement("canvas"); cv.width = W; cv.height = H;
        var g = cv.getContext("2d");
        var F = "'Pretendard Variable', Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif";
        g.fillStyle = "#0f1117"; g.fillRect(0, 0, W, H);
        var gr = g.createRadialGradient(80, 0, 0, 80, 0, 700); gr.addColorStop(0, "rgba(255,61,127,.20)"); gr.addColorStop(1, "rgba(255,61,127,0)");
        g.fillStyle = gr; g.fillRect(0, 0, W, H);
        // 로고(무지갯빛 원) + 이름
        var cg = g.createConicGradient ? g.createConicGradient(-Math.PI / 2, 110, 110) : null;
        if (cg) { ["#ff3d7f", "#ffd23d", "#18c4b0", "#6c7bff", "#ff3d7f"].forEach(function (col, i) { cg.addColorStop(i / 4, col); }); g.fillStyle = cg; }
        else g.fillStyle = "#ff3d7f";
        g.beginPath(); g.arc(110, 110, 34, 0, Math.PI * 2); g.fill();
        g.strokeStyle = "rgba(255,255,255,.45)"; g.lineWidth = 7; g.beginPath(); g.arc(110, 110, 30, 0, Math.PI * 2); g.stroke();
        g.fillStyle = "#eef0f7"; g.font = "800 46px " + F; g.textBaseline = "middle"; g.fillText("스포츠분석", 164, 110);
        var w = g.measureText("스포츠분석").width; g.fillStyle = "#ff3d7f"; g.font = "800 26px " + F; g.fillText(".kr", 170 + w, 118);
        g.fillStyle = "#eef0f7"; g.font = "800 60px " + F; g.fillText("내 조합 " + legs.length + "폴더", 76, 222);
        var y = 300;
        legs.forEach(function (l) {
          g.fillStyle = "#1a1d27"; g.strokeStyle = "#2c3140"; g.lineWidth = 2;
          if (g.roundRect) { g.beginPath(); g.roundRect(76, y, W - 152, rowH - 16, 20); g.fill(); g.stroke(); } else g.fillRect(76, y, W - 152, rowH - 16);
          g.fillStyle = "#8a90a6"; g.font = "600 24px " + F; g.fillText((l.no ? l.no + "번 · " : "") + (l.league || ""), 104, y + 28);
          g.fillStyle = "#eef0f7"; g.font = "700 32px " + F;
          var label = l.label; while (g.measureText(label).width > 560 && label.length > 4) label = label.slice(0, -2) + "…";
          g.fillText(label, 104, y + 64);
          g.font = "800 34px " + F; var ot = l.odds.toFixed(2), ow = g.measureText(ot).width;
          g.fillText(ot, W - 104 - ow, y + 46);
          g.font = "700 30px " + F; var pk = l.pick, pw = g.measureText(pk).width;
          g.fillStyle = toneC(pk);
          g.fillText(pk, W - 104 - ow - 28 - pw, y + 46);
          y += rowH;
        });
        y += 24;
        g.fillStyle = "#8a90a6"; g.font = "600 28px " + F; g.fillText("종합배당", 76, y + 20); g.fillText("예상 적중률", 560, y + 20);
        g.fillStyle = "#eef0f7"; g.font = "800 64px " + F; g.fillText("×" + c.odds.toFixed(2), 76, y + 84); g.fillText(pct(c.p), 560, y + 84);
        g.fillStyle = "#2c3140"; g.fillRect(76, H - 92, W - 152, 2);
        g.fillStyle = "#8a90a6"; g.font = "600 26px " + F; g.fillText("만 19세 이상 · 베트맨 공식 채널에서만 · 참고용 분석", 76, H - 50);
        g.fillStyle = "#c2c7d6"; g.font = "700 26px " + F; var u = "스포츠분석.kr"; g.fillText(u, W - 76 - g.measureText(u).width, H - 50);
        cv.toBlob(function (b) { resolve(b); }, "image/png");
      } catch (e) { resolve(null); }
    });
  }
  function shareSlip() {
    var legs = legsOf(slip.ids), c = calc(legs);
    if (!legs.length || !c) { toast("먼저 경기를 담아 주세요."); return; }
    var url = location.origin + "/?s=" + shareCode(slip.ids) + "&utm_source=share";
    var text = "내 조합 " + legs.length + "폴더 · 종합배당 " + c.odds.toFixed(2) + " (스포츠분석)";
    shareImage(legs, c).then(function (blob) {
      var file = blob && window.File ? new File([blob], "my-combo.png", { type: "image/png" }) : null;
      if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
        return navigator.share({ files: [file], title: "내 조합", text: text + "\n" + url }).catch(function () {});
      }
      if (navigator.share) return navigator.share({ title: "내 조합", text: text, url: url }).catch(function () {});
      // PC: 링크 복사 + 이미지 저장
      try { navigator.clipboard.writeText(url); } catch (e) {}
      if (blob) { var a = doc.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "내조합.png"; a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000); }
      toast("링크를 복사하고 이미지를 저장했습니다.");
    });
  }
  function importShared() {
    var m = /[?&]s=([^&]+)/.exec(location.search);
    if (!m) return;
    var ids = fromCode(decodeURIComponent(m[1]));
    try { history.replaceState(null, "", location.pathname + location.hash); } catch (e) {}
    if (!ids.length || !data) return;
    var live = ids.filter(function (id) { return byId[id]; });
    if (!live.length) { toast("공유받은 조합의 경기가 이미 시작했거나 마감됐습니다."); return; }
    slip.ids = [];
    addIds(live, true);
    toast("공유받은 조합 " + live.length + "경기를 담았습니다" + (live.length < ids.length ? " (시작한 경기 제외)" : "") + ".");
    if (slipEl) slipEl.classList.add("is-open");
  }
  $$("[data-slip-share]").forEach(function (b) { b.addEventListener("click", shareSlip); });
  loadData().then(function () { if (tool) renderToolList(""); render(); importShared(); });
})();
