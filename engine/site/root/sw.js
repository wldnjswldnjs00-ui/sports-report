/* 스포츠분석.kr 서비스 워커
   - 앱 설치(휴대폰·PC)와 알림을 위해 있다. 화면은 항상 네트워크에서 새로 받고(분석이 자주 바뀜),
     인터넷이 끊겼을 때만 마지막으로 본 화면을 보여준다.
   - 알림: 서버가 내용 없이 신호만 보내면, 여기서 /data/push.json 을 받아 알림을 띄운다. */
const CACHE = "sr-v1";

self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  if (req.mode === "navigate") {
    e.respondWith((async () => {
      try {
        const res = await fetch(req);
        const c = await caches.open(CACHE);
        c.put(req, res.clone());
        return res;
      } catch (err) {
        return (await caches.match(req)) || (await caches.match("/")) || Response.error();
      }
    })());
  }
});

self.addEventListener("push", (e) => {
  e.waitUntil((async () => {
    let d = { title: "스포츠분석", body: "새 분석이 올라왔습니다.", url: "/" };
    try {
      const r = await fetch("/data/push.json?t=" + Date.now(), { cache: "no-store" });
      if (r.ok) d = Object.assign(d, await r.json());
    } catch (err) {}
    await self.registration.showNotification(d.title, {
      body: d.body, icon: "/icon-192.png", badge: "/icon-192.png", tag: d.tag || "daily", renotify: true, data: { url: d.url },
    });
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  })());
});
