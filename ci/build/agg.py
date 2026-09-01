"""Jira 원본(raw/*.json) → 보드 데이터 상수. agg3.py를 CI용으로 옮긴 것.
명부는 코드에 두지 않는다 — BOARD_CONFIG 시크릿(JSON)에서 읽는다."""
import json, collections, os, datetime, sys

CFG = json.loads(os.environ['BOARD_CONFIG'])
ROSTER = CFG['roster']
UNIT = {r['name']: r['unit'] for r in ROSTER}
MGR  = {r['name'] for r in ROSTER if r.get('mgr')}

# 공개 리포에서는 Actions 로그도 공개다. 실명이 그대로 찍히면 명부가 새는 것과 같다.
# 기본은 가림(김*아), 확인이 필요할 때만 BOARD_VERBOSE=1 로 켠다.
VERBOSE = bool(os.environ.get('BOARD_VERBOSE'))
def mask(n):
    if VERBOSE or len(n) < 3: return n if VERBOSE else n[0] + '*' * (len(n) - 1)
    return n[0] + '*' * (len(n) - 2) + n[-1]

def load(name):
    return json.load(open(f'raw/{name}.json'))

def norm(n):
    f=n['fields']; p=f.get('parent') or {}
    return dict(k=n['key'], s=(f['summary'] or '').strip(), t=f['issuetype']['name'],
        st=f['status']['name'], cat=f['status']['statusCategory']['name'],
        a=(f['assignee']['displayName'].split('/')[0].strip() if f.get('assignee') else None),
        acct=(f['assignee']['accountId'] if f.get('assignee') else None),
        md=f.get('customfield_12766'), md2=f.get('customfield_12767'),
        created=(f.get('created') or '')[:10],
        p=p.get('key'), ps=((p.get('fields') or {}).get('summary') or '').strip() or None,
        pt=((p.get('fields') or {}).get('issuetype') or {}).get('name'))

WORK=[norm(n) for n in load('work')]
CONT=[norm(n) for n in load('cont')]

DROPPED={'Dropped','철회/반려/취소'}
CUT=CFG['jira'].get('createdFrom','2026-01-01')   # fetch.py 의 JQL 과 반드시 같아야 한다
drop=[x for x in WORK+CONT if x['created'] and x['created'] < CUT]
print('2026 이전 생성으로 제외:', len(drop), collections.Counter(x['t'] for x in drop))
d={}
_dr=0
for x in WORK+CONT:
    if x['created'] and x['created'] < CUT: continue
    if x['st'] in DROPPED: _dr+=1; continue      # 중단(Dropped·철회/반려/취소) 제외
    d.setdefault(x['k'], x)
print('중단으로 제외:', _dr)
ALL=list(d.values()); byk=d
print('전체 고유', len(ALL), collections.Counter(x['t'] for x in ALL))
print('Initiative 프로젝트:', collections.Counter(x['k'].split('-')[0] for x in ALL if x['t']=='Initiative'))

LEAF={'Design','Task','부작업','작업'}   # '작업'은 UXR 프로젝트의 실무 유형
V2FROM='2026-07-01'
# v2 버킷 — 네 상태는 이름으로 고정하고, 나머지 '진행 중' 카테고리는 전부 active로 보낸다.
# 이렇게 두면 새로운 진행 상태(Design Review, Hand-Off 등)가 생겨도 자동으로 잡힌다.
BR2={'active':0,'todo':1,'backlog':2,'hold':3,'done':4}
def v2b(x):
    st=x['st']
    if st=='SUGGESTED': return 'todo'
    if st=='Backlog':   return 'backlog'
    if st=='HOLD':      return 'hold'          # 카테고리는 '진행 중'이지만 멈춘 일이라 먼저 뺀다
    if x['cat']=='진행 중': return 'active'      # In Design·In Progress·Design Review·QA·Finalization…
    if x['cat']=='완료':   return 'done'        # 완료·Hand-Off·론치완료… (Dropped류는 앞에서 이미 제외)
    return None

def rootkey(x):
    """조상 체인의 최상위 키. 맵에 없는 부모라도 키 자체는 알 수 있다."""
    cur=x; last=x['k']
    for _ in range(6):
        pk=cur.get('p')
        if not pk: break
        last=pk
        if pk in byk: cur=byk[pk]
        else: break
    return last

def worktype(x):
    pj=rootkey(x).split('-')[0]
    if pj=='FT': return 'FT 과제'
    if pj=='TM': return '프로덕트 과제'
    return '운영·KTLO'

def chain(i):
    cur=i; out=[]
    for _ in range(6):
        pk=cur.get('p')
        if not pk: break
        if pk in byk: nxt=byk[pk]; out.append(nxt); cur=nxt
        else: out.append(dict(k=pk, s=cur.get('ps'), t=cur.get('pt'), a=None)); break
    return out

# ── 사람별 담당 집합 → 최상위만 남기기 ──
def bucket(x): return 'hold' if x['st']=='HOLD' else {'진행 중':'active','해야 할 일':'todo','완료':'done'}[x['cat']]
mine=collections.defaultdict(set)
for x in ALL:
    if x['a'] in UNIT: mine[x['a']].add(x['k'])
for x in ALL:
    x['w'] = worktype(x)

top=collections.defaultdict(list); rolled=collections.Counter(); kidmap=collections.defaultdict(list)
for x in ALL:
    n=x['a']
    if n not in UNIT: continue
    # 상위가 본인 담당이면 상태와 무관하게 흡수(하위로 접어 보여줌)
    owner=next((a['k'] for a in chain(x) if a['k'] in mine[n]), None)
    if owner: rolled[owner]+=1; kidmap[owner].append(x)
    else: top[n].append(x)

print('업무 유형:', collections.Counter(worktype(x) for x in ALL if x['a'] in UNIT))
BR={'active':0,'hold':1,'todo':2,'done':3}
CR={'진행 중':0,'해야 할 일':1,'완료':2}; TR={'Initiative':0,'Epic':1}
LOAD={}; DESIGN={}; ISSUES={}
for n,u in UNIT.items():
    def eff(x):
        """자신과 하위를 통틀어 가장 진행에 가까운 상태 (완료 상위에 진행 중 하위가 묻히지 않게)"""
        bs=[bucket(x)]+[bucket(y) for y in kidmap.get(x['k'],[])]
        return min(bs, key=lambda b: BR[b])
    items=sorted(top.get(n,[]), key=lambda x:(BR[eff(x)], TR.get(x['t'],2), x['k']))
    leaves=[x for x in ALL if x['a']==n and x['t'] in LEAF]
    L=dict(total=len(items), active=0, hold=0, todo=0, done=0, types={}, comp={}, all={}, epics={})
    L['allOwn']={}                       # v1 카드용 — 롤업 무시, 본인 담당 전체를 유형별로
    L['own7']={}                         # v2 카드·유형행용 — 같은 것을 V2FROM 이후 생성분으로만
    for x in ALL:
        if x['a']!=n: continue
        L['allOwn'][x['t']]=L['allOwn'].get(x['t'],0)+1
        if x['created']>=V2FROM: L['own7'][x['t']]=L['own7'].get(x['t'],0)+1
    for k in ['mdActive','mdHold','mdTodo','mdDone']: L[k]={'sum':0.0,'filled':0,'total':0}
    for x in items:
        b=eff(x); L[b]+=1
        L['types'][x['w']]=L['types'].get(x['w'],0)+1
        if b=='active': L['comp'][x['t']]=L['comp'].get(x['t'],0)+1
        L['all'][x['t']]=L['all'].get(x['t'],0)+1
    for x in leaves:                                  # MD는 실무 이슈에서만
        g=L['md'+bucket(x).capitalize()]
        g['total']+=1
        if x['md'] is not None: g['filled']+=1; g['sum']+=x['md']
    for k in ['mdActive','mdHold','mdTodo','mdDone']: L[k]['sum']=round(L[k]['sum'],1)
    L['own']=L['mdActive']['total']      # 본인 담당 진행 중 실무 이슈 수 (HOLD 제외) = 작업량
    L['ownHold']=L['mdHold']['total']
    LOAD[n]=L
    # ── v2용: 본인 담당 디자인 티켓 평면 목록 ──
    def proj(x):
        """프로젝트 단위 — 조상 체인에서 가장 위의 Initiative. 없으면 가장 가까운 Epic.
           Epic 두 개가 같은 Initiative 아래면 한 프로젝트로 묶인다."""
        cur, epic, init = x, None, None
        for _ in range(6):
            pk = cur.get('p')
            if not pk: break
            if pk not in byk:
                if init is None and pk.split('-')[0] == 'FT':
                    init = dict(k=pk, s=None, t='Initiative')
                elif epic is None:
                    epic = dict(k=pk, s=None, t='Epic')
                break
            cur = byk[pk]
            if cur['t'] == 'Initiative': init = dict(k=cur['k'], s=cur['s'], t='Initiative')
            elif cur['t'] == 'Epic' and epic is None: epic = dict(k=cur['k'], s=cur['s'], t='Epic')
        return init or epic
    def near(x):
        """가장 가까운 상위 Epic/Initiative (담당자 무관)"""
        cur=x
        for _ in range(6):
            pk=cur.get('p')
            if not pk: return None
            if pk not in byk: return dict(k=pk, s=None, t=('Initiative' if pk.split('-')[0]=='FT' else 'Epic'))
            cur=byk[pk]
            if cur['t'] in ('Epic','Initiative'): return dict(k=cur['k'], s=cur['s'], t=cur['t'])
        return None
    # v2 범위: 2026-07-01 이후 생성 + 상태가 In Design / 완료 / SUGGESTED 인 것만
    v2 = [x for x in leaves if x['created'] >= V2FROM and v2b(x)]
    DESIGN[n]=[dict(k=x['k'], s=x['s'], st=x['st'], b=v2b(x), t=x['t'], w=x['w'],
                    up=near(x), pj=proj(x), cr=x['created'], e=x['md'], a=x['md2'])
               for x in sorted(v2, key=lambda y:(BR2[v2b(y)], y['k']))]
    def kidrows(pk, depth=0):
        """직속 하위 → 그 하위까지 재귀로 중첩 (Initiative → Epic → Design)"""
        if depth > 3: return []
        ks=sorted(kidmap.get(pk,[]), key=lambda y:(TR.get(y['t'],2), BR[bucket(y)], y['k']))
        return [dict(k=y['k'], s=y['s'], st=y['st'], b=bucket(y), t=y['t'], md=y['md'],
                     kids=kidrows(y['k'], depth+1)) for y in ks]
    def total(rows):
        return sum(1 + total(r['kids']) for r in rows)
    def dsum(rows):
        """하위 실무 이슈(Design/Task/부작업)의 MD 합계 — 컨테이너 자체 MD는 세지 않는다"""
        S=F=T=0.0
        for r in rows:
            if r['t'] in LEAF:
                T+=1
                if r['md'] is not None: F+=1; S+=r['md']
            a,b,c=dsum(r['kids']); S+=a; F+=b; T+=c
        return S,F,T
    def annotate(rows):
        """Initiative/Epic은 자기 MD 대신 하위 디자인 MD 합계를 보여준다"""
        for r in rows:
            annotate(r['kids'])
            if r['t'] in ('Initiative','Epic'):
                S,F,T=dsum(r['kids'])
                r['dmd']=dict(s=round(S,2), f=int(F), t=int(T)) if T else None
                r['md']=None
    ISSUES[n]=[]
    for x in items:
        ks=kidrows(x['k'])
        annotate(ks)
        row=dict(k=x['k'],s=x['s'],st=x['st'],c=x['cat'],b=eff(x),t=x['t'],md=x['md'],w=x['w'],
                 sub=total(ks), kids=ks)
        annotate([row])
        ISSUES[n].append(row)

mem={n:v for n,v in LOAD.items() if n not in MGR}
KST = datetime.timezone(datetime.timedelta(hours=9))
# '지금 갱신' 버튼이 POST 할 Cloudflare Worker 엔드포인트. 리포 변수 REFRESH_API 로 주입한다.
# 값이 없으면 버튼은 숨은 채로 남는다 — 누를 대상이 없는 버튼을 보여주지 않기 위해서다.
META=dict(fetchedAt=datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
          refreshApi=(os.environ.get("REFRESH_API") or None),
          # 선택. Worker 에 REFRESH_KEY 를 설정했을 때만 넣는다. 값은 암호화된 보드 안에만 있다.
          refreshKey=(os.environ.get("REFRESH_KEY") or None),
          doneFrom=CFG['jira'].get('doneFrom', "2026-07-01"), createdFrom=CUT,
          workIssues=sum(v['total'] for v in mem.values()),
          activeIssues=sum(v['active'] for v in mem.values()),
          holdIssues=sum(v['hold'] for v in mem.values()))
print(META)
def band(n): return '여유' if n<=1 else '보통' if n<=4 else '많음' if n<=7 else '과부하'
print(f"{'이름':6s}{'작업량':>7s}{'보류':>5s}{'담당 전체':>13s}  뱃지")
for n in sorted(mem, key=lambda x:-mem[x]['own']):
    v=mem[n]
    print(f"{mask(n):6s}{v['own']:>7}{v['ownHold']:>5}{v['total']:>13}  {band(v['own']):5s}")
import collections as _c
print('분포:', dict(_c.Counter(band(v['own']) for v in mem.values())))
ACCT={}
for x in WORK+CONT:
    if x['a'] in UNIT and x['acct']: ACCT.setdefault(x['a'], x['acct'])
_miss=[n for n in UNIT if n not in ACCT]
print(f'ACCT {len(ACCT)}/{len(UNIT)}명' + (f' · 계정 못 찾음: {[mask(n) for n in _miss]}' if _miss else ' · 전원 매핑'))
if _miss: print('::warning::ACCT 매핑 누락 — ' + ', '.join(mask(n) for n in _miss))
json.dump(ACCT, open('ACCT.json','w'), ensure_ascii=False, indent=1)

print('MD 기입:', sum(1 for v in DESIGN.values() for x in v if x['e'] is not None), 'Estimate /',
      sum(1 for v in DESIGN.values() for x in v if x['a'] is not None), 'Actual')

for f,o in [('LOAD.json',LOAD),('ISSUES.json',ISSUES),('META.json',META),('DESIGN.json',DESIGN)]:
    json.dump(o,open(f,'w'),ensure_ascii=False)
