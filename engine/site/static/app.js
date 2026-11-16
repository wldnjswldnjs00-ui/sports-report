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
  var fDay = null, fSport = "all";
  function applyFilters() {
    $$(".match").forEach(function (m) {
      m.hidden = !((fSport === "all" || m.dataset.sport === fSport) && (!fDay || m.dataset.day === fDay));
    });
  }
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
    var chips = $$(".chip", box);
    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        chips.forEach(function (x) { x.setAttribute("aria-pressed", String(x === c)); });
        fSport = c.dataset.f; applyFilters();
      });
    });
  });
  applyFilters();

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
  var MAX_LEGS = 10;
  var CORR = 0.985;
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
    if (missing) return { odds: odds, p: null, ev: null, kelly: null };
    p *= Math.pow(CORR, pairs);
    var ev = p * odds - 1;
    var kelly = odds > 1 ? Math.max(0, (p * odds - 1) / (odds - 1)) * 0.25 : 0;
    return { odds: odds, p: p, ev: ev, kelly: kelly };
  }

  function pct(x, d) { return x == null ? "–" : (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  function sgn(x) { return x == null ? "–" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%"; }

  function addIds(ids, quiet) {
    if (!data) return;
    var added = 0, replaced = 0, past = 0;
    ids.forEach(function (id) {
      var l = byId[id];
      if (!l) { past++; return; }
      var idx = slip.ids.indexOf(id);
      if (idx >= 0) return;
      var same = slip.ids.filter(function (x) { return byId[x] && byId[x].match === l.match; });
      if (same.length) { slip.ids = slip.ids.filter(function (x) { return same.indexOf(x) < 0; }); replaced++; }
      if (slip.ids.length >= MAX_LEGS) return;
      slip.ids.push(id); added++;
    });
    save();
    if (!quiet) {
      if (past && !added) toast("오늘 발매 경기만 담을 수 있습니다.");
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
      var evEl = $("[data-slip-ev]");
      evEl.textContent = c ? sgn(c.ev) : "–";
      evEl.className = c && c.ev != null ? (c.ev > 0 ? "pos" : c.ev > -0.1 ? "mid" : "neg") : "";
      $("[data-slip-warn]").textContent = legs.length === 1 ? "프로토 승부식은 2경기 이상 묶어야 합니다." : "";
    }
    $$(".opick[data-leg]").forEach(function (b) { b.classList.toggle("is-on", slip.ids.indexOf(b.dataset.leg) >= 0); });
    renderTool(legs);
  }

  if (slipEl) {
    $("[data-slip-open]").addEventListener("click", function () { slipEl.classList.toggle("is-open"); });
    $("[data-slip-close]").addEventListener("click", function () { slipEl.classList.remove("is-open"); });
    $("[data-slip-clear]").addEventListener("click", function () { slip.ids = []; save(); toast("비웠습니다."); });
    doc.addEventListener("keydown", function (e) { if (e.key === "Escape") slipEl.classList.remove("is-open"); });
  }

  doc.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".opick[data-leg]");
    if (b) { e.stopPropagation(); toggleId(b.dataset.leg); return; }
    var c = e.target.closest && e.target.closest("[data-add-combo]");
    if (c) {
      try {
        var ids = JSON.parse(c.dataset.addCombo), outs = JSON.parse(c.dataset.addOutcomes);
        addIds(ids.map(function (id, i) { return id + "|" + outs[i]; }));
        if (slipEl && !slipEl.classList.contains("is-open")) slipEl.classList.add("is-open");
      } catch (err) {}
    }
  });

  /* ───── 계산기 페이지 ───── */
  var tool = $("[data-tool]"), manual = [];
  function renderTool(legs) {
    if (!tool) return;
    var all = legs.concat(manual);
    var ol = $("[data-tool-legs]");
    ol.innerHTML = "";
    legs.forEach(function (l, i) { ol.appendChild(legLi(l, i)); });
    manual.forEach(function (l, i) {
      var li = legLi(l, 0);
      li.querySelector("button").onclick = function (ev) { ev.stopPropagation(); manual.splice(i, 1); render(); };
      ol.appendChild(li);
    });
    var c = calc(all);
    $("[data-t-odds]").textContent = c ? c.odds.toFixed(2) : "–";
    $("[data-t-p]").textContent = c ? pct(c.p) : "–";
    var ev = $("[data-t-ev]");
    ev.textContent = c ? sgn(c.ev) : "–";
    ev.className = c && c.ev != null ? (c.ev > 0 ? "pos" : c.ev > -0.1 ? "mid" : "neg") : "";
    $("[data-t-kelly]").textContent = c && c.kelly != null ? pct(c.kelly) : "–";
    var bank = parseFloat($("[data-t-bank]").value) || 0, adv = $("[data-t-advice]");
    if (!c || c.p == null) adv.textContent = "";
    else if (c.ev <= 0) adv.textContent = "기대값이 마이너스입니다. 수학적으로는 사지 않는 쪽이 낫습니다. 산다면 잃어도 괜찮은 금액만.";
    else {
      var amt = Math.min(100000, Math.floor(bank * c.kelly / 100) * 100);
      adv.textContent = "기대값 플러스. 예산 기준 적정 금액은 약 " + amt.toLocaleString("ko-KR") + "원입니다.";
    }
  }
  function renderToolList(q) {
    var ul = $("[data-tool-list]");
    if (!data || !data.legs.length) { ul.innerHTML = '<li class="muted">오늘 발매 경기가 아직 없습니다.</li>'; return; }
    var groups = {};
    data.legs.forEach(function (l) { (groups[l.match] = groups[l.match] || []).push(l); });
    ul.innerHTML = "";
    q = (q || "").trim().toLowerCase();
    Object.keys(groups).forEach(function (k) {
      var g = groups[k], first = g[0];
      if (q && first.label.toLowerCase().indexOf(q) < 0) return;
      var li = doc.createElement("li");
      var head = doc.createElement("div");
      head.className = "tl-head";
      head.innerHTML = "<small></small>";
      head.querySelector("small").textContent = (first.no ? first.no + "번 " : "") + first.league;
      head.appendChild(doc.createTextNode(first.label));
      var row = doc.createElement("div");
      row.className = "odds-pick";
      g.forEach(function (l) {
        var b = doc.createElement("button");
        b.type = "button"; b.className = "opick"; b.dataset.leg = l.id;
        b.innerHTML = "<span></span><b></b>";
        b.querySelector("span").textContent = l.pick;
        b.querySelector("b").textContent = l.odds.toFixed(2);
        row.appendChild(b);
      });
      li.appendChild(head); li.appendChild(row);
      ul.appendChild(li);
    });
    render();
  }
  if (tool) {
    $("[data-tool-search]").addEventListener("input", function (e) { renderToolList(e.target.value); });
    $("[data-t-bank]").addEventListener("input", function () { render(); });
    $("[data-tool-manual]").addEventListener("submit", function (e) {
      e.preventDefault();
      var f = e.target, o = parseFloat(f.odds.value), p = parseFloat(f.p.value) / 100;
      if (!(o >= 1.01 && p > 0 && p < 1)) { toast("배당과 확률을 확인하세요."); return; }
      if (slip.ids.length + manual.length >= MAX_LEGS) { toast("최대 10경기까지입니다."); return; }
      manual.push({ id: "m" + Date.now(), label: "직접 입력", pick: (p * 100).toFixed(1) + "%", odds: o, p: p, league: "직접" + manual.length });
      f.reset();
      render();
    });
  }

  loadData().then(function () { if (tool) renderToolList(""); render(); });
})();
