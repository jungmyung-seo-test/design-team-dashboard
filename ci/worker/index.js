/**
 * pd-board-refresh — 보드의 '지금 갱신' 버튼이 부르는 유일한 엔드포인트.
 *
 * 브라우저가 지라를 직접 부르는 것은 불가능하다(토큰이 페이지에 박히고 CORS 도 막힌다).
 * 이 Worker 는 GitHub 토큰만 쥐고 있다가 Actions 워크플로를 대신 실행해 준다.
 * 지라 토큰은 여기에도 없다 — 그건 Actions 시크릿 안에만 있다.
 *
 * 바인딩
 *   GH_TOKEN        (시크릿) fine-grained PAT · 대상 리포 1개 · Actions: Read and write
 *   GH_REPO         owner/repo
 *   GH_REF          워크플로를 돌릴 브랜치 (기본 main)
 *   ALLOWED_ORIGIN  쉼표로 구분한 허용 Origin
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
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    };

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return reply({ error: 'POST only' }, 405, cors);
    if (!okOrigin) return reply({ error: 'forbidden origin' }, 403, cors);

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
    try {
      const r = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
      if (r.ok) {
        const run = (await r.json()).workflow_runs?.[0];
        if (run && (run.status === 'queued' || run.status === 'in_progress')) {
          return reply({ ok: true, already: true, startedAt: run.run_started_at }, 200, cors);
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
