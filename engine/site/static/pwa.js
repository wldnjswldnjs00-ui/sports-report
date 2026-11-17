/* 앱 설치(휴대폰·PC)와 매일 알림 구독.
   - 크롬·엣지·삼성 인터넷: 브라우저가 설치 가능하다고 알려주면 '앱으로 설치' 버튼을 보여준다.
   - 아이폰 사파리: 설치 버튼이 없어서 '공유 → 홈 화면에 추가' 안내를 보여준다(홈 화면 앱에서만 알림 가능).
   - 알림: 서버(/api/push)가 켜져 있을 때만 '알림 받기' 버튼을 보여준다. */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;
  var bar = document.querySelector("[data-appbar]");
  var bInstall = document.querySelector("[data-install]");
  var bPush = document.querySelector("[data-push]");
  var msg = document.querySelector("[data-app-msg]");
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  };
  var standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  var ios = /iPhone|iPad|iPod/.test(navigator.userAgent) && !window.MSStream;
  var deferred = null, reg = null;

  function show() { if (bar && ((bInstall && !bInstall.hidden) || (bPush && !bPush.hidden) || bar.dataset.tip)) bar.hidden = false; }
  function say(t) { if (msg) msg.textContent = t; }

  navigator.serviceWorker.register("/sw.js").then(function (r) { reg = r; return setupPush(); }).catch(function () {});

  /* 설치 */
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferred = e;
    if (bInstall && !standalone) { bInstall.hidden = false; show(); }
  });
  window.addEventListener("appinstalled", function () {
    if (bInstall) bInstall.hidden = true;
    say("설치했습니다. 홈 화면(또는 PC 앱 목록)의 스포츠분석 아이콘으로 바로 열 수 있습니다.");
  });
  if (bInstall) bInstall.addEventListener("click", function () {
    if (!deferred) return;
    deferred.prompt();
    deferred.userChoice.finally(function () { deferred = null; bInstall.hidden = true; });
  });
  if (ios && !standalone && bar) {
    bar.dataset.tip = "1";
    say("아이폰: 아래 공유 버튼 → '홈 화면에 추가'를 누르면 앱처럼 쓰고 알림도 받을 수 있습니다.");
    show();
  }

  /* 알림 */
  function urlB64(s) {
    var p = "=".repeat((4 - (s.length % 4)) % 4), b = atob((s + p).replace(/-/g, "+").replace(/_/g, "/"));
    var a = new Uint8Array(b.length);
    for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i);
    return a;
  }
  function pushOn(on) {
    if (!bPush) return;
    bPush.textContent = on ? "알림 끄기" : "알림 받기";
    bPush.dataset.on = on ? "1" : "";
  }
  function setupPush() {
    if (!bPush || !("PushManager" in window) || !("Notification" in window)) return;
    if (ios && !standalone) return; // 아이폰은 홈 화면 앱에서만 알림 가능
    return fetch("/api/push/key", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d || !d.key) return;
      bPush.dataset.key = d.key;
      return reg.pushManager.getSubscription().then(function (s) {
        pushOn(!!s);
        bPush.hidden = false;
        show();
      });
    }).catch(function () {});
  }
  if (bPush) bPush.addEventListener("click", function () {
    if (!reg) return;
    bPush.disabled = true;
    var done = function () { bPush.disabled = false; };
    if (bPush.dataset.on) {
      reg.pushManager.getSubscription().then(function (s) {
        if (!s) return;
        return fetch("/api/push/unsubscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: s.endpoint }) })
          .then(function () { return s.unsubscribe(); });
      }).then(function () { pushOn(false); say("알림을 껐습니다."); }).finally(done);
      return;
    }
    Notification.requestPermission().then(function (p) {
      if (p !== "granted") { say("알림이 차단돼 있습니다. 브라우저 주소창 왼쪽 자물쇠 → 알림 허용으로 바꿀 수 있습니다."); return; }
      return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64(bPush.dataset.key) }).then(function (s) {
        return fetch("/api/push/subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: s.endpoint }) });
      }).then(function (r) {
        if (r && r.ok) { pushOn(true); say("매일 오후 7시쯤 다음 구매일 분석이 올라오면 알려드립니다."); store.set("push", "1"); }
        else say("알림 등록에 실패했습니다. 잠시 뒤 다시 눌러 주세요.");
      });
    }).catch(function () { say("이 브라우저는 알림을 지원하지 않습니다."); }).finally(done);
  });
})();
