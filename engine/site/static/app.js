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

  /* 레일: 10초마다 자동으로 다음 카드, 손대면 멈춤 */
  $$("[data-rail]").forEach(function (rail) {
    var n = rail.children.length, hold = false, timer;
    if (n < 2 || reduce) return;
    function next() {
      if (hold || doc.hidden) return;
      var w = rail.clientWidth + 16, i = Math.round(rail.scrollLeft / w);
      rail.scrollTo({ left: ((i + 1) % n) * w, behavior: "smooth" });
    }
    var inside = false, touching = false, wheelT;
    function sync() {
      var was = hold; hold = inside || touching;
      if (was && !hold) { clearInterval(timer); timer = setInterval(next, 10000); } // 손을 뗀 뒤 10초를 처음부터 다시 센다
    }
    rail.addEventListener("mouseenter", function () { inside = true; sync(); });
    rail.addEventListener("mouseleave", function () { inside = false; sync(); });
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
  var fDay = null, fSport = "all";
  function applyFilters() {
    var shown = 0;
    $$(".match").forEach(function (m) {
      m.hidden = !((fSport === "all" || m.dataset.sport === fSport) && (!fDay || m.dataset.day === fDay));
      if (!m.hidden) shown++;
    });
    var em = $("[data-empty]");
    if (em) em.hidden = shown > 0;
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
  function pct(x) { return x == null ? "–" : (x * 100).toFixed(x < 0.1 ? 1 : 0) + "%"; }
  /* 권장 금액: 켈리 기준. f = (p × 배당 − 1) ÷ (배당 − 1), 그 1/4 만 건다(쿼터 켈리).
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
      $("[data-slip-warn]").textContent = "";
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
    if (!c || c.p == null || !B) {
      $("[data-t-stake]").textContent = "–"; $("[data-t-pay]").textContent = "–";
      adv.textContent = !B ? "총 시드를 입력하세요." : !legs.length ? "경기를 고르면 권장 금액이 나옵니다." : "";
      return;
    }
    var s = stakeFor(c.p, c.odds, B), pay = Math.floor(s.stake * c.odds / 10) * 10;
    $("[data-t-stake]").textContent = won(s.stake);
    $("[data-t-pay]").textContent = won(pay);
    var fp = (s.f * 100).toFixed(s.f < 0.01 ? 2 : 1).replace(/\.?0+$/, "") + "%";
    adv.textContent = "총 시드 " + won(B) + "의 " + fp + (s.capped ? "는 1회 한도를 넘어 " : "인 ") + won(s.stake) + " 베팅을 권장합니다. 맞을 확률은 " + pct(c.p) +
      "이고, 맞으면 " + won(pay) + "을 받습니다." + (legs.length === 1 ? " 한 경기 구매는 베트맨에서 '한경기구매' 표시가 있는 경기만 가능합니다." : "");
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
      $(".tl-meta", head).textContent = (f.no ? f.no + "번 · " : "") + f.league + (ko ? " · " + (+ko.slice(5, 7)) + "/" + (+ko.slice(8, 10)) + " " + ko.slice(11, 16) : "");
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

  /* 조합 카드 권장 금액: "시드 30만 원의 1.5% = 4,500원" (계산기와 같은 시드·같은 기준) */
  var seedEl = $("[data-seed]");
  function seedVal() {
    var v = seedEl ? parseInt(String(seedEl.value).replace(/[^0-9]/g, ""), 10) : 0;
    if (!v) v = parseInt(store.get("budget"), 10) || 300000;
    return Math.min(MAX_SEED, v);
  }
  function paintStakes() {
    var B = seedVal();
    $$("[data-stake]").forEach(function (el) {
      var p = parseFloat(el.dataset.p), o = parseFloat(el.dataset.odds);
      if (!(p > 0) || !(o > 1)) { el.hidden = true; return; }
      var s = stakeFor(p, o, B), fp = (s.f * 100).toFixed(s.f < 0.01 ? 2 : 1).replace(/\.?0+$/, "") + "%";
      el.innerHTML = "<span></span><b></b>";
      el.querySelector("span").textContent = "시드 " + won(B) + "의 " + fp + (s.capped ? " (1회 한도)" : "");
      el.querySelector("b").textContent = won(s.stake) + " 권장";
    });
  }
  if (seedEl) {
    var sv = parseInt(store.get("budget"), 10);
    if (sv) seedEl.value = sv.toLocaleString("ko-KR");
    seedEl.addEventListener("input", function () {
      var v = Math.min(MAX_SEED, parseInt(String(seedEl.value).replace(/[^0-9]/g, ""), 10) || 0);
      seedEl.value = v ? v.toLocaleString("ko-KR") : "";
      if (v) store.set("budget", v);
      paintStakes();
    });
  }
  paintStakes();

  loadData().then(function () { if (tool) renderToolList(""); render(); });
})();
