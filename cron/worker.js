// 스포츠분석.kr 예약 실행: 정해진 시각에 GitHub Actions '매일 분석' 워크플로를 시작한다.
// - 사이트 파일(dist/)은 그대로 정적 자산으로 나가고, 이 스크립트는 예약 실행(scheduled)에만 쓰인다.
// - GH_TOKEN: Cloudflare 대시보드의 비밀 값(이 저장소 Actions 쓰기 권한만 있는 fine-grained 토큰). 코드·저장소에는 없다.
const REPO = "wldnjswldnjs00-ui/sports-report";
const WORKFLOW = "daily.yml";

function slotOf(event) {
  // 묶어 둔 cron("0 4,9,... * * *")은 실제 실행 시각(UTC)으로 워크플로의 slot 문자열을 만든다
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
    if (r.status === 401 || r.status === 403 || r.status === 404 || r.status === 422) return; // 토큰·권한 문제는 다시 해도 같다
    await new Promise((res) => setTimeout(res, 5000 * (i + 1)));
  }
}

export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(slotOf(event), env));
  },
};
