// 스포츠분석.kr Worker
// 1) 예약 실행: 정해진 시각에 GitHub Actions '매일 분석' 워크플로를 시작한다(GH_TOKEN 은 Cloudflare 비밀 값).
// 2) 알림(웹 푸시): /api/push/* 로 구독을 받아 KV(PUSH)에 두고, 19:20(KST)에 "다음 구매일 분석 공개" 알림을 보낸다.
//    알림 내용은 보내지 않고 신호만 보낸다(서비스 워커가 /data/push.json 을 받아 띄움). 그래서 암호화가 필요 없다.
//    서명 키(VAPID)는 처음 쓸 때 Worker 가 스스로 만들어 KV 에 둔다. 사람이 다룰 비밀 값이 없다.
//    KV 가 연결되지 않았으면 알림 기능만 꺼지고 사이트·예약 실행은 그대로 동작한다.
const REPO = "wldnjswldnjs00-ui/sports-report";
const WORKFLOW = "daily.yml";
// Cloudflare 무료 계정은 계정 전체에 예약 실행이 5개까지라(다른 Worker 와 나눠 씀) 이 Worker 는 하나만 쓴다:
// 5분마다 깨어나 아래 표의 시각(UTC "HH:MM")일 때만 일을 한다. 그 밖의 시각에는 아무것도 하지 않는다.
const SCHEDULE = {
  "14:05": "5 14 * * *",  // 23:05 KST 다음 구매일 리포트
  "21:00": "0 21 * * *",  // 06:00 새 리포트 + 전날 채점
  "22:00": "0 22 * * *",  // 07:00 재수집 + 쓰레드 아침
  "00:30": "30 0 * * *",  // 09:30 재수집
  "02:00": "0 2 * * *",   // 11:00 쓰레드 전날 결과
  "04:00": "0 4 * * *",   // 13:00 재수집
  "06:00": "0 6 * * *",   // 15:00 쓰레드 노하우
  "09:00": "0 9 * * *",   // 18:00 해외 배당 새로고침
  "10:00": "0 10 * * *",  // 19:00 다음 구매일 분석 공개 + 쓰레드 저녁
  "13:00": "0 13 * * *",  // 22:00 다음 구매일 분석(쓰레드 저녁·노하우 예비)
};
const PUSH_AT = "10:20"; // 19:20 KST 알림
const SITE = "https://xn--sr3bw9dq7a9xy85g.kr";

function hhmm(event) {
  // 예정 시각을 5분 단위로 맞춰 읽는다(실행이 몇 초 늦어도 같은 칸)
  const d = new Date(Math.round(event.scheduledTime / 300000) * 300000);
  return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0");
}

async function dispatch(slot, env) {
  if (!env.GH_TOKEN) { console.log("GH_TOKEN 없음: 예약 실행을 건너뜀"); return; }
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  for (let i = 0; i < 3; i++) {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sports-report-cron",
      },
      body: JSON.stringify({ ref: "main", inputs: { slot } }),
    });
    if (r.status === 204) { console.log(`시작함: ${slot}`); return true; }
    const body = await r.text();
    console.log(`실패 ${r.status} (${slot}): ${body.slice(0, 300)}`);
    if (r.status === 401 || r.status === 403 || r.status === 404 || r.status === 422) return;
    await new Promise((res) => setTimeout(res, 5000 * (i + 1)));
  }
}

// ───────── 빠짐 없이 실행하기(자가 복구) ─────────
// 정해진 시각부터 WINDOW 분 동안, 깨어날 때마다 "그 시각의 실행이 GitHub 에 이미 있는지" 확인하고 없을 때만 시작한다.
// - 한 번 깨어남이 빠지거나 GitHub 요청이 실패해도 5분 뒤 다시 시도 → 40분 안에 저절로 복구
// - 이미 있으면 아무것도 안 함 → 여러 경로(Cloudflare 예약, 외부 호출 /api/tick, 예비 커밋)가 겹쳐도 한 번만 실행
// - 끝까지 실행이 안 생기면 GitHub 이슈로 알린다(토큰에 Issues 권한이 있을 때, 이메일 알림)
const WINDOW = 40; // 분
const GH = (env) => ({
  Authorization: `Bearer ${env.GH_TOKEN}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "sports-report-cron",
});

function dueSlots(now) {
  // 지금 기준으로 창(시작~+WINDOW분) 안에 있는 시각들: [{slot, start(ms), age(분)}]
  const out = [];
  for (const [t, slot] of Object.entries(SCHEDULE)) {
    const [h, m] = t.split(":").map(Number);
    for (const dayShift of [0, -1]) {
      const d = new Date(now);
      d.setUTCDate(d.getUTCDate() + dayShift);
      d.setUTCHours(h, m, 0, 0);
      const age = (now - d.getTime()) / 60000;
      if (age >= 0 && age < WINDOW) out.push({ slot, start: d.getTime(), age });
    }
  }
  return out;
}

// 무료 요금제는 예약 실행 1번에 CPU 10ms 까지라, 큰 JSON 을 해석하지 않는다.
// 1) 우리가 시작한 기록(KV)이 있으면 끝. 2) 없으면 GitHub 실행 목록(수동 시작분, 최근 10개)을 글자 그대로 찾아본다.
const ranKey = (slot, start) => `ran:${slot}:${new Date(start).toISOString().slice(0, 10)}`;

async function alreadyRan(slot, start, env) {
  if (env.PUSH && await env.PUSH.get(ranKey(slot, start))) return true;
  const since = new Date(start - 10 * 60000).toISOString().slice(0, 19) + "Z";
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=10&created=%3E%3D${since}`;
  const r = await fetch(url, { headers: GH(env) });
  if (!r.ok) throw new Error(`실행 목록 ${r.status}`);
  const text = await r.text();
  return text.includes(`매일 분석 · ${slot}"`) || text.includes(`[slot:${slot}]`);
}

async function note(env, msg) {
  // 마지막 상태만 덮어쓴다(값에 비밀 없음). /api/status 로 확인
  if (!env.PUSH) return;
  try { await env.PUSH.put("cronlog", JSON.stringify({ at: new Date().toISOString(), msg })); } catch (e) {}
}

async function alert(slot, env) {
  // 같은 날 같은 시각 경고는 한 번만(제목으로 중복 확인)
  const title = `⚠️ 정기 실행 누락: ${slot} (${new Date().toISOString().slice(0, 10)})`;
  const q = await fetch(`https://api.github.com/repos/${REPO}/issues?state=open&per_page=50`, { headers: GH(env) });
  if (q.ok && (await q.json()).some((i) => i.title === title)) return;
  const r = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
    method: "POST", headers: GH(env),
    body: JSON.stringify({ title, body: `정해진 시각(${slot}, UTC)부터 ${WINDOW}분 동안 실행이 생기지 않았습니다.\n\nActions 탭에서 '매일 분석'을 직접 실행(Run workflow, slot 에 \`${slot}\`)하면 됩니다.\n원인 후보: GitHub 토큰 만료·권한, GitHub Actions 장애.` }),
  });
  console.log(`누락 경고 이슈 ${r.status}`);
}

async function ensure(now, env) {
  const due = dueSlots(now);
  if (!due.length) return;
  if (!env.GH_TOKEN) { console.log("GH_TOKEN 없음"); await note(env, "GH_TOKEN 없음"); return; }
  for (const { slot, start, age } of due) {
    try {
      if (await alreadyRan(slot, start, env)) continue;
      if (age >= WINDOW - 5) { await alert(slot, env); await note(env, `누락 경고 ${slot}`); continue; }
      const ok = await dispatch(slot, env);
      if (ok && env.PUSH) await env.PUSH.put(ranKey(slot, start), "1", { expirationTtl: 172800 });
      await note(env, ok ? `시작 ${slot}` : `시작 실패 ${slot}`);
    } catch (e) {
      console.log(`확인 실패 ${slot}: ${e}`); // 다음 깨어남(5분 뒤)에 다시
      await note(env, `확인 실패 ${slot}: ${String(e).slice(0, 80)}`);
    }
  }
}

// 외부 호출(/api/tick)이 너무 잦으면 무시(1분에 한 번만 처리)
async function throttled() {
  const key = new Request("https://tick.internal/last");
  const c = caches.default;
  if (await c.match(key)) return true;
  await c.put(key, new Response("1", { headers: { "Cache-Control": "max-age=60" } }));
  return false;
}

// ───────── 웹 푸시 ─────────
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const enc = (s) => new TextEncoder().encode(s);

async function vapid(env) {
  let v = await env.PUSH.get("vapid", "json");
  if (!v) {
    const kp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
    v = { priv: await crypto.subtle.exportKey("jwk", kp.privateKey), pub: b64u(await crypto.subtle.exportKey("raw", kp.publicKey)) };
    await env.PUSH.put("vapid", JSON.stringify(v));
  }
  return v;
}

async function jwt(aud, v) {
  const key = await crypto.subtle.importKey("jwk", v.priv, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const head = b64u(enc(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const body = b64u(enc(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: SITE })));
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc(`${head}.${body}`));
  return `${head}.${body}.${b64u(sig)}`;
}

async function keyOf(endpoint) {
  return "s:" + b64u(await crypto.subtle.digest("SHA-256", enc(endpoint))).slice(0, 32);
}

async function sendAll(env) {
  if (!env.PUSH) { console.log("PUSH(KV) 없음: 알림을 건너뜀"); return; }
  const v = await vapid(env);
  const tokens = {};
  let cursor, sent = 0, gone = 0;
  do {
    const page = await env.PUSH.list({ prefix: "s:", cursor });
    for (const k of page.keys) {
      const sub = await env.PUSH.get(k.name, "json");
      if (!sub || !sub.endpoint) continue;
      const aud = new URL(sub.endpoint).origin;
      tokens[aud] = tokens[aud] || await jwt(aud, v);
      const r = await fetch(sub.endpoint, {
        method: "POST",
        headers: { TTL: "21600", Urgency: "normal", Authorization: `vapid t=${tokens[aud]}, k=${v.pub}`, "Content-Length": "0" },
      });
      if (r.status === 404 || r.status === 410) { await env.PUSH.delete(k.name); gone++; } else if (r.ok) sent++;
      else console.log(`알림 실패 ${r.status}: ${(await r.text()).slice(0, 200)}`);
    }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  console.log(`알림 보냄 ${sent}, 만료 삭제 ${gone}`);
}

const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });

async function api(request, env, path) {
  if (!env.PUSH) return json({ ok: false, reason: "off" }, 503);
  if (path === "/api/push/key" && request.method === "GET") return json({ key: (await vapid(env)).pub });
  if (request.method !== "POST") return json({ ok: false }, 405);
  const origin = request.headers.get("Origin");
  if (origin && origin !== SITE && !origin.endsWith("스포츠분석.kr")) return json({ ok: false }, 403);
  let body;
  try { body = await request.json(); } catch (e) { return json({ ok: false }, 400); }
  const ep = body && body.endpoint;
  if (!ep || typeof ep !== "string" || !/^https:\/\//.test(ep) || ep.length > 1000) return json({ ok: false }, 400);
  if (path === "/api/push/subscribe") {
    await env.PUSH.put(await keyOf(ep), JSON.stringify({ endpoint: ep, at: Date.now() }));
    return json({ ok: true });
  }
  if (path === "/api/push/unsubscribe") {
    await env.PUSH.delete(await keyOf(ep));
    return json({ ok: true });
  }
  return json({ ok: false }, 404);
}

// ───────── 쓰레드 토큰 보관·자동 연장 ─────────
// 쓰레드 장기 토큰은 60일이면 만료된다. 토큰을 KV(PUSH, 비공개)에만 두고, 이 Worker 가 7일마다 스스로 연장한다.
// GitHub 자동 실행은 게시할 때 /api/tt 로 최신 토큰을 받아 간다. 요청자는 GitHub 이 발급한 OIDC 신원 증명(JWT)으로 확인한다:
//   발급자 token.actions.githubusercontent.com, 대상 "sports-report-worker", 저장소 REPO 일 때만 응답(따로 둘 비밀 값 없음).
// 처음 한 번은 GitHub Secrets 의 토큰을 함께 보내 KV 에 넣고(KV 에 없을 때만), 그 뒤로는 KV 의 토큰을 연장해 쓴다.
const OIDC_ISS = "https://token.actions.githubusercontent.com";
const OIDC_AUD = "sports-report-worker";
const TT_EVERY = 7 * 24 * 3600 * 1000;

const b64uToBytes = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));

async function verifyGithub(jwt) {
  const parts = String(jwt || "").split(".");
  if (parts.length !== 3) return null;
  let head, claims;
  try {
    head = JSON.parse(new TextDecoder().decode(b64uToBytes(parts[0])));
    claims = JSON.parse(new TextDecoder().decode(b64uToBytes(parts[1])));
  } catch (e) { return null; }
  if (head.alg !== "RS256" || claims.iss !== OIDC_ISS || claims.aud !== OIDC_AUD || claims.repository !== REPO) return null;
  const now = Math.floor(Date.now() / 1000);
  if (!(claims.exp > now) || (claims.nbf && claims.nbf > now + 60)) return null;
  const jwks = await (await fetch(OIDC_ISS + "/.well-known/jwks", { cf: { cacheTtl: 3600 } })).json();
  const jwk = (jwks.keys || []).find((k) => k.kid === head.kid);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey("jwk", { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64uToBytes(parts[2]), new TextEncoder().encode(parts[0] + "." + parts[1]));
  return ok ? claims : null;
}

async function ttRefresh(env, force = false) {
  if (!env.PUSH) return null;
  const st = await env.PUSH.get("tt", "json");
  if (!st || !st.token) return st;
  if (!force && Date.now() - (st.refreshed || 0) < TT_EVERY) return st;
  const r = await fetch(`https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=${encodeURIComponent(st.token)}`);
  if (!r.ok) {
    st.error = { at: Date.now(), status: r.status, body: (await r.text()).slice(0, 200).replace(st.token, "***") };
    await env.PUSH.put("tt", JSON.stringify(st));
    console.log(`쓰레드 토큰 연장 실패 ${r.status}`);
    return st;
  }
  let d = {};
  try { d = await r.json(); } catch (e) { return st; } // 이상한 응답이면 기존 토큰을 그대로 쓴다
  if (!d.access_token) return st;
  const next = { token: d.access_token, refreshed: Date.now(), expires: Date.now() + (Number(d.expires_in) || 0) * 1000 };
  await env.PUSH.put("tt", JSON.stringify(next));
  console.log(`쓰레드 토큰 연장 완료(만료 ${new Date(next.expires).toISOString().slice(0, 10)})`);
  return next;
}

async function ttApi(request, env) {
  if (!env.PUSH) return json({ ok: false, reason: "off" }, 503);
  if (request.method !== "POST") return json({ ok: false }, 405);
  const auth = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  const who = await verifyGithub(auth);
  if (!who) return json({ ok: false }, 401);
  let body = {};
  try { body = await request.json(); } catch (e) {}
  let st = await env.PUSH.get("tt", "json");
  const seedOk = body.seed && typeof body.seed === "string" && body.seed.length > 20;
  // KV 토큰이 없거나, 이미 만료됐는데 GitHub Secrets 에 새 토큰이 들어온 경우 그 토큰으로 다시 시작
  if (seedOk && (!st || !st.token || (st.expires && st.expires < Date.now() && st.token !== body.seed.trim()))) {
    st = { token: body.seed.trim(), refreshed: 0, expires: 0 }; // 처음 한 번: GitHub Secrets 토큰을 넣고 바로 연장
    await env.PUSH.put("tt", JSON.stringify(st));
  }
  if (!st || !st.token) return json({ ok: false, reason: "empty" }, 404);
  st = (await ttRefresh(env)) || st;
  return json({ ok: true, token: st.token, expires: st.expires || null, error: st.error || null });
}

// ───────── 쓰레드 예약 게시(GitHub 실행이 멈춰도 동작하는 예비 경로) ─────────
// 사이트에 배포된 /data/tq.json(게시 대기열)을 보고, 정해진 시각이 되면 KV 에 보관한 쓰레드 토큰으로 직접 올린다.
// 대기열 항목: {id, at(ms), images:[주소], text}. 한 번 올린 항목은 KV(tq:<id>)에 기록해 두 번 올리지 않는다.
const TAPI = "https://graph.threads.net/v1.0";
async function tq(env, now) {
  if (!env.PUSH) return;
  let q = [];
  try { const r = await env.ASSETS.fetch(new Request(SITE + "/data/tq.json")); if (r.ok) q = await r.json(); } catch (e) { return; }
  for (const it of q || []) {
    if (!it || !it.id || !(now >= it.at) || now > it.at + 3 * 3600e3) continue;
    const key = "tq:" + it.id, mark = await env.PUSH.get(key);
    if (mark === "done" || mark === "busy") continue;
    const tries = Number((mark || "").replace("fail", "")) || 0;
    if (tries >= 3) continue;
    await env.PUSH.put(key, "busy", { expirationTtl: 900 });
    let ok = false, why = "";
    try { ok = await tpost(env, it); } catch (e) { why = String(e).slice(0, 160); }
    await env.PUSH.put(key, ok ? "done" : "fail" + (tries + 1), { expirationTtl: 7 * 86400 });
    await note(env, ok ? `쓰레드 게시 ${it.id}` : `쓰레드 게시 실패 ${it.id} ${why}`);
  }
}
async function tpost(env, it) {
  const st = await env.PUSH.get("tt", "json");
  if (!st || !st.token) throw new Error("토큰 없음");
  const tk = encodeURIComponent(st.token);
  const me = await (await fetch(`${TAPI}/me?fields=id&access_token=${tk}`)).json();
  if (!me.id) throw new Error("me " + JSON.stringify(me).slice(0, 120));
  const post = async (params) => {
    const u = `${TAPI}/${me.id}/threads?` + new URLSearchParams({ ...params, access_token: st.token });
    const j = await (await fetch(u, { method: "POST" })).json();
    if (!j.id) throw new Error("생성 " + JSON.stringify(j).slice(0, 160));
    return j.id;
  };
  const ready = async (id, wait) => {
    for (let i = 0; i < wait / 4; i++) {
      const j = await (await fetch(`${TAPI}/${id}?fields=status,error_message&access_token=${tk}`)).json();
      if (j.status === "FINISHED") return true;
      if (j.status === "ERROR" || j.status === "EXPIRED") throw new Error("처리 " + (j.error_message || j.status));
      await new Promise((r) => setTimeout(r, 4000));
    }
    return false;
  };
  const imgs = it.images || [];
  let cid;
  if (imgs.length > 1) {
    const kids = [];
    for (const u of imgs.slice(0, 20)) kids.push(await post({ media_type: "IMAGE", image_url: u, is_carousel_item: "true" }));
    for (const k of kids) await ready(k, 120);
    cid = await post({ media_type: "CAROUSEL", children: kids.join(","), text: it.text || "" });
  } else if (imgs.length === 1) {
    cid = await post({ media_type: "IMAGE", image_url: imgs[0], text: it.text || "" });
  } else {
    cid = await post({ media_type: "TEXT", text: it.text || "" });
  }
  await ready(cid, 120);
  const pub = await (await fetch(`${TAPI}/${me.id}/threads_publish?` + new URLSearchParams({ creation_id: cid, access_token: st.token }), { method: "POST" })).json();
  if (!pub.id) throw new Error("게시 " + JSON.stringify(pub).slice(0, 160));
  if (it.link) {
    // 링크는 본문 대신 바로 아래 답글로(추천 피드 도달 유지). 실패해도 본 글은 그대로
    try {
      await new Promise((r) => setTimeout(r, 4000));
      let rid;
      try { rid = await post({ media_type: "TEXT", text: it.link_text || "전체 내용은 여기서", reply_to_id: pub.id, link_attachment: it.link }); }
      catch (e) { rid = await post({ media_type: "TEXT", text: (it.link_text || "전체 내용은 여기서") + "\n" + it.link, reply_to_id: pub.id }); }
      await ready(rid, 40);
      await fetch(`${TAPI}/${me.id}/threads_publish?` + new URLSearchParams({ creation_id: rid, access_token: st.token }), { method: "POST" });
    } catch (e) { /* 답글은 덤 */ }
  }
  return true;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    // 검색엔진용 주소 하나로 모으기: http → https, www → 대표 주소, /index.html·끝 슬래시 없는 주소 → 슬래시 주소(모두 영구 301)
    if (request.method === "GET" || request.method === "HEAD") {
      let to = null;
      if (url.protocol === "http:") { url.protocol = "https:"; to = url; }
      if (url.hostname.startsWith("www.")) { url.hostname = url.hostname.slice(4); to = url; }
      if (path.endsWith("/index.html")) { url.pathname = path.slice(0, -10); to = url; }
      else if (!path.endsWith("/") && !path.startsWith("/api/") && !/\.[A-Za-z0-9]{1,8}$/.test(path)) { url.pathname = path + "/"; to = url; }
      if (to) return new Response(null, { status: 301, headers: { Location: to.toString(), "Cache-Control": "public, max-age=86400" } });
    }
    if (path === "/api/tick") {
      // 예비 깨우기 주소: 외부 무료 예약 서비스가 5분마다 부르면, Cloudflare 예약이 멈춰도 같은 확인-후-실행이 돈다
      if (await throttled()) return json({ ok: true, skipped: "too soon" });
      await ensure(Date.now(), env);
      return json({ ok: true });
    }
    if (path === "/api/status") {
      // 예약 실행이 살아 있는지 확인용(비밀 값 없음): 마지막 깨어남 시각과 마지막 시작 기록
      const hb = env.PUSH ? await env.PUSH.get("hb") : null;
      const log = env.PUSH ? await env.PUSH.get("cronlog", "json") : null;
      return json({ ok: true, cron_last: hb, last: log, kv: !!env.PUSH, gh: !!env.GH_TOKEN, names: Object.keys(env).sort() }); // 이름만(값 없음)
    }
    if (path === "/api/tt") {
      try { return await ttApi(request, env); } catch (e) { return json({ ok: false, err: String(e && e.message || e).slice(0, 160) }, 500); } // 원인 확인용(비밀 값 없음)
    }
    if (path.startsWith("/api/push/")) {
      try { return await api(request, env, path); } catch (e) { return json({ ok: false }, 500); }
    }
    return env.ASSETS.fetch(request);
  },
  async scheduled(event, env, ctx) {
    const t = hhmm(event);
    if (t === PUSH_AT) ctx.waitUntil(sendAll(env));
    ctx.waitUntil(ensure(event.scheduledTime, env));
    // 살아 있음 표시: 15분마다 한 번만 쓴다(KV 무료 쓰기 한도 보호)
    if (env.PUSH && /:(00|15|30|45)$/.test(t)) {
      ctx.waitUntil(env.PUSH.put("hb", new Date(event.scheduledTime).toISOString()).catch(() => null));
    }
    ctx.waitUntil(ttRefresh(env).catch(() => null)); // 7일마다 쓰레드 토큰 연장(지났을 때만)
    ctx.waitUntil(tq(env, event.scheduledTime).catch(() => null)); // 쓰레드 예약 게시(대기열이 있을 때만)
  },
};
