#!/usr/bin/env python3
"""Jira Cloud REST → raw/{work,cont,one}.json

이전 파이프라인은 MCP 도구가 남긴 tool-result 파일을 읽었다. 그 파일은 세션이
끝나면 사라지므로 어느 환경에서도 갱신을 재현할 수 없었다. 이 스크립트가 그
자리를 대신한다 — 지라를 직접 조회해 agg.py/one.py 가 기대하는 형태로 떨군다.

출력은 `[{key, fields:{...}}, ...]` 리스트다. MCP 응답의 `issues.nodes` 와 같은
모양이라 집계 코드를 고치지 않아도 된다.

환경변수: JIRA_EMAIL · JIRA_TOKEN · BOARD_CONFIG
"""
import base64, json, os, sys, time, urllib.error, urllib.request

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


def call(path, body=None, tries=4):
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


def search(jql, fields):
    """신형 /search/jql (nextPageToken). 없으면 구형 /search (startAt) 로 폴백."""
    out, token, page = [], None, 0
    while True:
        body = {'jql': jql, 'maxResults': 100, 'fields': fields}
        if token:
            body['nextPageToken'] = token
        try:
            r = call('/rest/api/3/search/jql', body)
        except SystemExit:
            if page == 0:
                print('  /search/jql 실패 — 구형 /search 로 폴백', flush=True)
                return search_legacy(jql, fields)
            raise
        out += r.get('issues') or []
        page += 1
        token = r.get('nextPageToken')
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


def main():
    os.makedirs('raw', exist_ok=True)
    counts = {}
    for name, q in QUERIES.items():
        print(f'[{name}] {q["jql"][:110]}…', flush=True)
        issues = normalize(search(q['jql'], q['fields']))
        if not issues:
            raise SystemExit(f'{name}: 0건 — JQL 또는 권한을 확인하세요. '
                             '빈 결과로 보드를 덮어쓰지 않기 위해 중단합니다.')
        json.dump(issues, open(f'raw/{name}.json', 'w'), ensure_ascii=False)
        counts[name] = len(issues)
        print(f'[{name}] {len(issues)}건 → raw/{name}.json\n', flush=True)
    print('조회 완료:', counts)


if __name__ == '__main__':
    main()
