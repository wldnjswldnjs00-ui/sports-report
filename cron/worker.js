// 스포츠분석.kr Worker
// 1) 예약 실행: 정해진 시각에 GitHub Actions '매일 분석' 워크플로를 시작한다(GH_TOKEN 은 Cloudflare 비밀 값).
// 2) 알림(웹 푸시): /api/push/* 로 구독을 받아 KV(PUSH)에 두고, 19:20(KST)에 "다음 구매일 분석 공개" 알림을 보낸다.
//    알림 내용은 보내지 않고 신호만 보낸다(서비스 워커가 /data/push.json 을 받아 띄움). 그래서 암호화가 필요 없다.
//    서명 키(VAPID)는 처음 쓸 때 Worker 가 스스로 만들어 KV 에 둔다. 사람이 다룰 비밀 값이 없다.
//    KV 가 연결되지 않았으면 알림 기능만 꺼지고 사이트·예약 실행은 그대로 동작한다.
const REPO = "wldnjswldnjs00-ui/sports-report";
const WORKFLOW = "daily.yml";
const PUSH_CRON = "20 10 * * *"; // 19:20 KST
const SITE = "https://xn--sr3bw9dq7a9xy85g.kr";

function slotOf(event) {
  if (event.cron === "5 14 * * *" || event.cron === "30 0 * * *") return event.cron;
  const h = new Date(event.scheduledTime).getUTCHours();
  return `0 ${h} * * *`;
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
    if (r.status === 204) { console.log(`시작함: ${slot}`); return; }
    const body = await r.text();
    console.log(`실패 ${r.status} (${slot}): ${body.slice(0, 300)}`);
    if (r.status === 401 || r.status === 403 || r.status === 404 || r.status === 422) return;
    await new Promise((res) => setTimeout(res, 5000 * (i + 1)));
  }
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

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path.startsWith("/api/push/")) {
      try { return await api(request, env, path); } catch (e) { return json({ ok: false }, 500); }
    }
    return env.ASSETS.fetch(request);
  },
  async scheduled(event, env, ctx) {
    if (event.cron === PUSH_CRON) { ctx.waitUntil(sendAll(env)); return; }
    ctx.waitUntil(dispatch(slotOf(event), env));
  },
};
