/**
 * pd-board-refresh — 보드의 '지금 갱신' 버튼이 부르는 유일한 엔드포인트.
 *
 * 브라우저가 지라를 직접 부르는 것은 불가능하다(토큰이 페이지에 박히고 CORS 도 막힌다).
 * 이 Worker 는 GitHub 토큰만 쥐고 있다가 Actions 워크플로를 대신 실행해 준다.
 * 지라 토큰은 여기에도 없다 — 그건 Actions 시크릿 안에만 있다.
 *
 * 바인딩
 *   GH_TOKEN        (시크릿) fine-grained PAT · 대상 리포 1개 · Actions: Read and write
 *   REFRESH_KEY     (시크릿, 선택) 보드가 보내는 공유 키. 설정하면 검사하고, 없으면 검사하지 않는다
 *   GH_REPO         owner/repo
 *   GH_REF          워크플로를 돌릴 브랜치 (기본 main)
 *   ALLOWED_ORIGIN  쉼표로 구분한 허용 Origin
 *   COOLDOWN_SEC    직전 실행 종료 후 이 시간 안에는 다시 실행하지 않는다 (기본 90)
 *
 * ALLOWED_ORIGIN 은 보안 장치가 아니다 — 브라우저용 CORS 설정일 뿐이고 curl 로는 헤더
 * 하나면 통과한다. 실제 문턱은 REFRESH_KEY 다. 그 값은 암호화된 보드 안에만 있으므로
 * "주소를 아는 사람"이 아니라 "보드 비밀번호를 아는 사람"만 갱신을 걸 수 있다.
 */
const WORKFLOW = 'refresh.yml';

const reply = (body, status, cors) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...cors },
  });

export default {
  async fetch(request, env) {
    const allowed = (env.ALLOWED_ORIGIN || '')
      .split(',').map(s => s.trim()).filter(Boolean);
    const origin = request.headers.get('Origin') || '';
    const okOrigin = allowed.length === 0 || allowed.includes(origin);

    const cors = {
      'Access-Control-Allow-Origin': okOrigin && origin ? origin : (allowed[0] || '*'),
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Board-Key',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    };

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return reply({ error: 'POST only' }, 405, cors);
    if (!okOrigin) return reply({ error: 'forbidden origin' }, 403, cors);

    // 공유 키 — 설정돼 있을 때만 검사한다(없으면 이 단계를 건너뛴다).
    if (env.REFRESH_KEY && request.headers.get('X-Board-Key') !== env.REFRESH_KEY) {
      return reply({ error: 'unauthorized' }, 401, cors);
    }

    const gh = (path, init = {}) =>
      fetch(`https://api.github.com/repos/${env.GH_REPO}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${env.GH_TOKEN}`,
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'pd-board-refresh',
          ...(init.headers || {}),
        },
      });

    // 이미 돌고 있으면 또 실행하지 않는다.
    // 26명이 동시에 눌러도 워크플로는 한 번만 돌고, 나머지는 그 실행을 함께 기다린다.
    // 방금 끝났으면 짧은 쿨다운을 둔다 — 연타로 지라를 반복 조회하는 것만 막는 목적이다.
    // 길게 잡으면 안 된다: "지라에서 티켓 고치고 바로 눌러 본다"가 정상적인 사용이라,
    // 그걸 막으면 사용자는 갱신이 고장난 것으로 받아들인다. 실행 1회가 40초쯤이므로
    // 30초면 연타만 걸러진다. 진짜 남용 방어는 쿨다운이 아니라 REFRESH_KEY 다.
    const cooldownMs = (Number(env.COOLDOWN_SEC) || 30) * 1000;
    try {
      const r = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
      if (r.ok) {
        const run = (await r.json()).workflow_runs?.[0];
        if (run && (run.status === 'queued' || run.status === 'in_progress')) {
          return reply({ ok: true, already: true, startedAt: run.run_started_at }, 200, cors);
        }
        if (run && run.updated_at) {
          const since = Date.now() - Date.parse(run.updated_at);
          if (since >= 0 && since < cooldownMs) {
            return reply({ ok: true, recent: true, agoSec: Math.round(since / 1000) }, 200, cors);
          }
        }
      }
    } catch (e) {
      // 상태 조회가 실패해도 갱신 자체는 시도한다.
    }

    const d = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, {
      method: 'POST',
      body: JSON.stringify({ ref: env.GH_REF || 'main' }),
    });
    if (d.status !== 204) {
      const detail = (await d.text()).slice(0, 300);
      return reply({ error: 'dispatch failed', status: d.status, detail }, 502, cors);
    }
    return reply({ ok: true, already: false }, 200, cors);
  },
};
