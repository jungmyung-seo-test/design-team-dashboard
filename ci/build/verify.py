#!/usr/bin/env python3
"""게시 전 검증 게이트. 실패하면 배포하지 않는다.

과거 사고는 대부분 "검증 목록이 사람이 손으로 고쳐야 하는 프롬프트에 살아 있어서"
생겼다. 구조를 바꿨는데 체크리스트를 못 따라가 보드가 5일간 멈춘 적도 있다.
그래서 여기서는 매직 넘버를 박지 않고 **서로 맞아야 하는 값끼리 비교**한다.
탭이 3개든 4개든 상관없다 — 탭 버튼 수와 뷰 섹션 수가 같기만 하면 된다.
"""
import json, os, re, sys

CFG    = json.loads(os.environ['BOARD_CONFIG'])
ROSTER = CFG['roster']
NAMES  = {r['name'] for r in ROSTER}
UNITS_CFG = {r['unit'] for r in ROSTER}
FLOOR  = CFG.get('expect', {}).get('minIssues', 100)

HERE = os.path.dirname(os.path.abspath(__file__))

# 공개 리포에서는 Actions 로그도 공개다. 검증 실패 메시지에도 실명을 그대로 쓰지 않는다.
VERBOSE = bool(os.environ.get('BOARD_VERBOSE'))
def mask(n):
    if VERBOSE: return n
    return n[0] + '*' * (len(n) - 2) + n[-1] if len(n) > 2 else n[0] + '*'

errs, warns = [], []
def bad(m):  errs.append(m)
def warn(m): warns.append(m)

LOAD   = json.load(open('LOAD.json'))
DESIGN = json.load(open('DESIGN.json'))
ACCT   = json.load(open('ACCT.json'))
META   = json.load(open('META.json'))
ONE    = json.load(open('ONE.json'))
page   = open('_plain.html', encoding='utf-8').read()
shell  = open(os.path.join(HERE, 'shell.html'), encoding='utf-8').read()

# ── 1. 명부 — 한 명이라도 비면 그 사람 카드가 통째로 사라진다 ──────────────
for label, d in [('LOAD', LOAD), ('DESIGN', DESIGN), ('ACCT', ACCT)]:
    miss  = NAMES - set(d)
    extra = set(d) - NAMES
    if miss:  bad(f'{label}: 명부에 있는데 없음 {len(miss)}명 — {", ".join(mask(x) for x in sorted(miss))}')
    if extra: bad(f'{label}: 명부에 없는 인원 {len(extra)}명 — {", ".join(mask(x) for x in sorted(extra))}')

# ── 2. META — createdFrom 누락으로 개인 지라 링크가 전부 깨진 적이 있다 ────
for k in ('fetchedAt', 'createdFrom', 'doneFrom'):
    if not META.get(k):
        bad(f'META.{k} 가 비었다')

# ── 3. 업무 유형·소속 — 템플릿의 정의와 데이터가 어긋나면 행이 사라진다 ────
wtypes = set(re.findall(r'\{k:"([^"]+)",\s*v:"--w\d+"\}', shell))
units  = set(re.findall(r'"([^"]+)"', re.search(r'const UNITS = \[([^\]]+)\]', shell).group(1)))
if not wtypes:
    bad('shell.html 에서 WTYPES 를 못 읽었다 (템플릿 구조 변경?)')
if units != UNITS_CFG:
    bad(f'소속 불일치 — 템플릿 {sorted(units)} vs 명부 {sorted(UNITS_CFG)}')

BUCKETS = {'active', 'todo', 'backlog', 'hold', 'done'}
total = 0
for n, items in DESIGN.items():
    total += len(items)
    byw = {}
    byb = {}
    for x in items:
        byw[x['w']] = byw.get(x['w'], 0) + 1
        byb[x['b']] = byb.get(x['b'], 0) + 1
        if x['w'] not in wtypes:
            bad(f'{mask(n)} {x["k"]}: 템플릿에 없는 업무 유형 "{x["w"]}"')
        if x['b'] not in BUCKETS:
            bad(f'{mask(n)} {x["k"]}: 알 수 없는 상태 버킷 "{x["b"]}"')
    # 유형 행 합계 ≠ 목록 총계 사고 재발 방지
    if sum(byw.values()) != len(items):
        bad(f'{mask(n)}: 유형 합계 {sum(byw.values())} ≠ 목록 {len(items)}')
    if sum(byb.values()) != len(items):
        bad(f'{mask(n)}: 상태 합계 {sum(byb.values())} ≠ 목록 {len(items)}')

if total < FLOOR:
    bad(f'티켓 총계 {total}건 — 하한 {FLOOR}건 미만이다. 조회가 반쪽이 났을 수 있다')

# ── 4. ONE 탭 ─────────────────────────────────────────────────────────────
if set(ONE.get('groups', {})) != UNITS_CFG:
    bad(f'ONE 그룹 불일치 — {sorted(ONE.get("groups", {}))}')
if not ONE.get('issues'):
    bad('ONE 이슈가 0건이다')

# ── 5. 렌더 산출물 ────────────────────────────────────────────────────────
if '__DATA__' in page:
    bad('_plain.html 에 __DATA__ 자리표시자가 남아 있다')
tabs     = len(re.findall(r'class="tab[" ]', page))
sections = len(re.findall(r'<section[^>]*id="view-', page))
if tabs != sections:
    bad(f'탭 {tabs}개 ≠ 뷰 섹션 {sections}개')     # 매직 넘버 대신 상호 일치를 본다
if not tabs:
    bad('탭을 하나도 못 찾았다 (템플릿 구조 변경?)')

data_blob = re.search(r'const DESIGN = (.*?);\nconst ACCT', page, re.S)
if data_blob and re.search(r'\bundefined\b|:\s*NaN\b', data_blob.group(1)):
    bad('주입된 데이터에 undefined/NaN 이 들어 있다')

# ── 6. 경고 (배포는 막지 않음) ────────────────────────────────────────────
active = sum(1 for v in DESIGN.values() for x in v if x['b'] == 'active')
if active == 0:
    warn('진행 중 티켓이 0건이다 — 상태 카테고리 매핑을 확인하세요')

print(f'인원 {len(DESIGN)}명 · 티켓 {total}건 · 진행 중 {active}건 · '
      f'탭 {tabs}개 · 유형 {len(wtypes)}종 · 스냅샷 {META.get("fetchedAt")}')
for w in warns:
    print(f'::warning::{w}')
if errs:
    for e in errs:
        print(f'::error::{e}')
    sys.exit(f'\n검증 실패 {len(errs)}건 — 배포하지 않습니다.')
print('검증 통과')
