#!/usr/bin/env python3
"""Jira Cloud REST → raw/{work,cont,one}.json

이전 파이프라인은 MCP 도구가 남긴 tool-result 파일을 읽었다. 그 파일은 세션이
끝나면 사라지므로 어느 환경에서도 갱신을 재현할 수 없었다. 이 스크립트가 그
자리를 대신한다 — 지라를 직접 조회해 agg.py/one.py 가 기대하는 형태로 떨군다.

출력은 `[{key, fields:{...}}, ...]` 리스트다. MCP 응답의 `issues.nodes` 와 같은
모양이라 집계 코드를 고치지 않아도 된다.

환경변수: JIRA_EMAIL · JIRA_TOKEN · BOARD_CONFIG
"""
import base64, collections, json, os, sys, time, urllib.error, urllib.request

CFG   = json.loads(os.environ['BOARD_CONFIG'])
J     = CFG['jira']
BASE  = J['baseUrl'].rstrip('/')
GROUP = J['groupId']
CREATED_FROM = J.get('createdFrom', '2026-01-01')
DONE_FROM    = J.get('doneFrom',    '2026-07-01')

AUTH = base64.b64encode(
    f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_TOKEN']}".encode()).decode()
HEAD = {'Authorization': f'Basic {AUTH}', 'Accept': 'application/json',
        'Content-Type': 'application/json', 'User-Agent': 'pd-role-board/1'}

FIELDS = ['summary', 'issuetype', 'status', 'parent', 'assignee',
          'customfield_12766', 'customfield_12767', 'created', 'resolutiondate']

MEMBERS = f'assignee IN membersOf("id:{GROUP}")'
SCOPE   = (f'{MEMBERS} AND created >= "{CREATED_FROM}" '
           f'AND (statusCategory != Done OR resolved >= "{DONE_FROM}")')

QUERIES = {
    'work': dict(
        jql=f'issuetype IN (Design, Task, 부작업, 작업) AND {SCOPE} ORDER BY key ASC',
        fields=FIELDS),
    'cont': dict(
        jql=f'issuetype IN (Epic, Initiative) AND {SCOPE} ORDER BY key ASC',
        fields=FIELDS),
    'one': dict(
        jql=J['oneJql'].replace('__GROUP__', GROUP),
        fields=FIELDS + ['labels']),
}

# statusCategory.name 은 호출 계정의 로케일에 따라 영문으로 올 수 있다.
# 집계 코드는 한국어('진행 중'…)를 기대하므로, 로케일과 무관한 key 로 고정한다.
# 이걸 안 하면 모든 티켓이 버킷 미분류로 떨어져 보드가 통째로 빈다.
CATKEY = {'new': '해야 할 일', 'indeterminate': '진행 중', 'done': '완료'}


class SoftFail(Exception):
    """이 요청만 실패했다는 뜻. 전체 조회를 중단시키지 않는다."""


def call(path, body=None, tries=4, soft=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=HEAD,
                                 method='POST' if data else 'GET')
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode(errors='replace')[:400]
            if e.code in (429, 502, 503, 504) and n < tries - 1:
                wait = int(e.headers.get('Retry-After') or 2 ** (n + 1))
                print(f'  {e.code} — {wait}s 뒤 재시도', flush=True)
                time.sleep(wait); continue
            if soft:
                raise SoftFail(f'{e.code} {body_txt[:120]}')
            raise SystemExit(f'Jira {e.code} {path}\n{body_txt}')
        except urllib.error.URLError as e:
            if n < tries - 1:
                time.sleep(2 ** (n + 1)); continue
            raise SystemExit(f'Jira 연결 실패 {path}: {e}')


def normalize(issues):
    """statusCategory 를 로케일 무관하게 되돌린다."""
    for it in issues:
        sc = ((it.get('fields') or {}).get('status') or {}).get('statusCategory')
        if sc and sc.get('key') in CATKEY:
            sc['name'] = CATKEY[sc['key']]
    return issues


def search(jql, fields, soft=False, quiet=False):
    """신형 /search/jql (nextPageToken). 없으면 구형 /search (startAt) 로 폴백."""
    out, token, page = [], None, 0
    while True:
        body = {'jql': jql, 'maxResults': 100, 'fields': fields}
        if token:
            body['nextPageToken'] = token
        try:
            r = call('/rest/api/3/search/jql', body, soft=soft)
        except SystemExit:
            if page == 0:
                print('  /search/jql 실패 — 구형 /search 로 폴백', flush=True)
                return search_legacy(jql, fields)
            raise
        out += r.get('issues') or []
        page += 1
        token = r.get('nextPageToken')
        if not quiet:
            print(f'  page {page}: +{len(r.get("issues") or [])} (누적 {len(out)})', flush=True)
        if not token or r.get('isLast'):
            break
        if page > 60:
            raise SystemExit('페이지 상한 초과 — JQL 확인 필요')
    return out


def search_legacy(jql, fields):
    out, start = [], 0
    while True:
        r = call('/rest/api/3/search',
                 {'jql': jql, 'startAt': start, 'maxResults': 100, 'fields': fields})
        got = r.get('issues') or []
        out += got
        start += len(got)
        print(f'  startAt {start} (누적 {len(out)})', flush=True)
        if not got or start >= r.get('total', 0):
            break
    return out


def parent_keys(issues):
    out = set()
    for n in issues:
        p = (n.get('fields') or {}).get('parent') or {}
        if p.get('key'):
            out.add(p['key'])
    return out


def by_keys(keys, fields):
    """키로 직접 가져온다. 한 배치가 실패하면 반으로 쪼개 살릴 수 있는 만큼 살린다.
       (없는 키·권한 없는 키가 하나 섞이면 그 배치 전체가 에러로 떨어지기 때문)"""
    keys = sorted(keys)
    out = []
    stack = [keys[i:i + 80] for i in range(0, len(keys), 80)]
    while stack:
        chunk = stack.pop()
        try:
            out += search('key IN (' + ','.join(chunk) + ')', fields, soft=True, quiet=True)
        except SoftFail as e:
            if len(chunk) == 1:
                print(f'  건너뜀 {chunk[0]}: {e}', flush=True)
            else:
                mid = len(chunk) // 2
                stack += [chunk[:mid], chunk[mid:]]
    return out


def ancestors(seed):
    """조상 체인을 끝까지 잇는다.

    work/cont 조회는 `assignee IN membersOf(디자인실)` 로 묶여 있다. 그래서 상위
    Epic·Initiative 가 다른 팀 담당이면 아예 조회되지 않고, 조상 추적이 거기서
    끊긴다. 그러면 최상위가 TM 인 과제도 중간 프로젝트 키에서 멈춰 운영·KTLO 로
    잘못 분류된다 (예: PD-8865 → MDC Epic → TM-3111).

    담당자·생성일 조건 없이 부모 키를 따라 직접 가져와 그 구멍을 메운다.
    이 결과는 체인 추적에만 쓰고 집계 건수에는 넣지 않는다.
    """
    known = {i['key'] for i in seed}
    out, pending = [], parent_keys(seed) - known
    for depth in range(6):
        if not pending:
            break
        got = normalize(by_keys(pending, FIELDS))
        if not got:
            break
        out += got
        known |= {i['key'] for i in got}
        print(f'  {depth + 1}단계: 부모 {len(pending)}개 요청 → {len(got)}건 확보', flush=True)
        pending = parent_keys(got) - known
    return out


def main():
    os.makedirs('raw', exist_ok=True)
    counts, fetched = {}, {}
    for name, q in QUERIES.items():
        print(f'[{name}] {q["jql"][:110]}…', flush=True)
        issues = normalize(search(q['jql'], q['fields']))
        if not issues:
            raise SystemExit(f'{name}: 0건 — JQL 또는 권한을 확인하세요. '
                             '빈 결과로 보드를 덮어쓰지 않기 위해 중단합니다.')
        json.dump(issues, open(f'raw/{name}.json', 'w'), ensure_ascii=False)
        counts[name] = len(issues)
        fetched[name] = issues
        print(f'[{name}] {len(issues)}건 → raw/{name}.json\n', flush=True)

    print('[anc] 끊긴 조상 체인 잇기', flush=True)
    anc = ancestors(fetched['work'] + fetched['cont'])
    json.dump(anc, open('raw/anc.json', 'w'), ensure_ascii=False)
    counts['anc'] = len(anc)
    pref = collections.Counter(i['key'].split('-')[0] for i in anc)
    print(f'[anc] {len(anc)}건 → raw/anc.json · 접두어 {dict(pref.most_common(12))}\n', flush=True)

    print('조회 완료:', counts)


if __name__ == '__main__':
    main()
