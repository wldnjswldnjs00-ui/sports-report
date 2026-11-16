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
    ["pointerdown", "touchstart", "wheel", "focusin", "mouseenter"].forEach(function (ev) {
      rail.addEventListener(ev, function () { hold = true; clearTimeout(timer); timer = setTimeout(function () { hold = false; }, 9000); }, { passive: true });
    });
    setInterval(next, 10000);
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
  var MAX_LEGS = 10, MAX_BUDGET = 100000, CORR = 0.985;
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
  /* 권장 금액: 맞을 확률이 낮은 조합일수록 예산의 작은 몫만 */
  function stakeFor(p, budget) {
    var f = p >= 0.6 ? 0.5 : p >= 0.3 ? 0.25 : p >= 0.1 ? 0.1 : p >= 0.03 ? 0.05 : 0.02;
    var s = Math.floor(budget * f / 100) * 100;
    return { f: f, stake: Math.min(MAX_BUDGET, Math.max(budget >= 100 ? 100 : 0, s)) };
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
    return Math.min(MAX_BUDGET, v);
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
    if (!c || c.p == null || legs.length < 2 || !B) {
      $("[data-t-stake]").textContent = "–"; $("[data-t-pay]").textContent = "–";
      adv.textContent = !B ? "예산을 입력하세요." : legs.length < 2 ? "경기를 2개 이상 고르면 권장 금액이 나옵니다." : "";
      return;
    }
    var s = stakeFor(c.p, B), pay = Math.floor(s.stake * c.odds / 10) * 10;
    $("[data-t-stake]").textContent = won(s.stake);
    $("[data-t-pay]").textContent = won(pay);
    adv.textContent = "예산 " + won(B) + " 중 " + Math.round(s.f * 100) + "%인 " + won(s.stake) + "을 권장합니다. 이 조합이 맞을 확률은 " + pct(c.p) +
      "이고, 맞으면 " + won(pay) + "을 받습니다. 남은 " + won(B - s.stake) + "은 다른 조합에 나눠 쓰세요.";
  }
  function renderToolList(q) {
    var ul = $("[data-tool-list]");
    if (!data || !data.legs.length) { ul.innerHTML = '<li class="muted">지금 발매 중인 경기가 없습니다.</li>'; return; }
    var groups = {};
    data.legs.forEach(function (l) { (groups[l.match + "|" + l.mk] = groups[l.match + "|" + l.mk] || []).push(l); });
    ul.innerHTML = "";
    q = (q || "").trim().toLowerCase();
    Object.keys(groups).forEach(function (k) {
      var g = groups[k], first = g[0];
      if (q && first.label.toLowerCase().indexOf(q) < 0) return;
      var li = doc.createElement("li"), head = doc.createElement("div"), row = doc.createElement("div");
      head.className = "tl-head"; head.innerHTML = "<small></small>";
      head.querySelector("small").textContent = (first.no ? first.no + "번 " : "") + first.league + (first.mkl ? " · " + first.mkl : "");
      head.appendChild(doc.createTextNode(first.label));
      row.className = "odds-pick";
      g.forEach(function (l) {
        var b = doc.createElement("button");
        b.type = "button"; b.className = "opick"; b.dataset.leg = l.id;
        b.innerHTML = "<span></span><b></b>";
        b.querySelector("span").textContent = l.pick;
        b.querySelector("b").textContent = l.odds.toFixed(2);
        row.appendChild(b);
      });
      li.appendChild(head); li.appendChild(row); ul.appendChild(li);
    });
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

  loadData().then(function () { if (tool) renderToolList(""); render(); });
})();
