#!/usr/bin/env python3
"""raw/one.json → ONE.json  (one3.py 를 CI용으로 옮긴 것)

meta·groups 는 이전 산출물을 물려받지 않고 BOARD_CONFIG 에서 새로 만든다.
물려받기는 과거에 ACCT 가 옛 매핑에 고정돼 5명의 유형 행이 사라진 사고의 원인이었다.
"""
import collections, json, os

CFG    = json.loads(os.environ['BOARD_CONFIG'])
GROUPS = CFG['oneGroups']
OMETA  = CFG['oneMeta']

LBTEAM = {'one밀도감_코어UX': 'Core UX Design', 'one밀도감_디스커버리': 'Discovery Design',
          'one밀도감_인게이지먼트': 'Engagement Design', 'one밀도감_커머스': 'Commerce Design'}
DROP = {'Dropped', '철회/반려/취소'}

# 칸반 5컬럼이 아는 상태. 새 상태가 생기면 경고로 알린다(조용히 사라지지 않게).
KNOWN = {'Backlog', 'SUGGESTED', 'P-Backlog', '기획완료', '디자인중', 'In Design', 'In Progress',
         '디자인완료', 'Design Finalization', 'Hand-Off', '개발중', '개발완료', '론치완료',
         '완료', '배포완료', 'HOLD', 'Dropped', '철회/반려/취소'}

nodes = json.load(open('raw/one.json'))
rows = []
for r, n in enumerate(nodes):
    f = n['fields']
    p = f.get('parent') or {}
    lb = [x for x in (f.get('labels') or []) if x in LBTEAM]
    a = f['assignee']['displayName'].split('/')[0].strip() if f.get('assignee') else None
    rows.append(dict(
        k=n['key'], s=(f['summary'] or '').strip(), t=f['issuetype']['name'],
        pj=n['key'].split('-')[0], st=f['status']['name'],
        cat=f['status']['statusCategory']['name'], a=a, md=f.get('customfield_12766'),
        rank=r, lb=lb, team=(LBTEAM[lb[0]] if lb else None),
        p=p.get('key'), ps=((p.get('fields') or {}).get('summary') or '').strip() or None))

ONE = dict(
    meta={**OMETA, 'total': len(rows),
          'labeled': sum(1 for x in rows if x['lb']),
          'ft': sum(1 for x in rows if x['pj'] == 'FT'),
          'pd': sum(1 for x in rows if x['pj'] == 'PD'),
          'active': sum(1 for x in rows if x['cat'] == '진행 중' and x['st'] not in DROP)},
    issues=rows, groups=GROUPS,
    assignees=sorted({x['a'] for x in rows if x['a']}))

json.dump(ONE, open('ONE.json', 'w'), ensure_ascii=False)
print('ONE', len(rows), '· 상태', dict(collections.Counter(x['st'] for x in rows)))
unknown = {x['st'] for x in rows} - KNOWN
if unknown:
    print('::warning::ONE 칸반 컬럼에 없는 상태 — ' + ', '.join(sorted(unknown)))
