#!/usr/bin/env python3
"""shell.html + 집계 JSON → 평문 보드 (_plain.html) + dist/status.json

로컬 mk.py 와의 차이는 하나다. 로컬본은 TEAM·JIRA·MANAGERS 세 상수를 직전
data.js 에서 문자열로 긁어와 다시 써넣는다(자기참조). data.js 가 깨지면 빌드가
죽고, CI 에는 그 파일이 아예 없다. 여기서는 셋 다 BOARD_CONFIG 에서 만든다 —
roster 로 TEAM 이 필드·순서까지 그대로 복원되는 것을 확인하고 옮겼다.
"""
import json, os, re

CFG    = json.loads(os.environ['BOARD_CONFIG'])
ROSTER = CFG['roster']
HERE   = os.path.dirname(os.path.abspath(__file__))

TEAM = [dict(name=r['name'], unit=r['unit'], focus=[], services=[], note='',
             role=r['role']) for r in ROSTER]
MANAGERS = [r['name'] for r in ROSTER if r.get('mgr')]
JIRA = CFG['jira']['baseUrl'].rstrip('/')

D = lambda o: json.dumps(o, ensure_ascii=False)
j = lambda f: json.load(open(f))

blob = (f"const TEAM = {D(TEAM)};\n"
        f"const LOAD = {D(j('LOAD.json'))};\n"
        f"const META = {D(j('META.json'))};\n"
        f"const DESIGN = {D(j('DESIGN.json'))};\n"
        f"const ACCT = {D(j('ACCT.json'))};\n"
        f"const JIRA = {D(JIRA)};\n"
        f"const MANAGERS = {D(MANAGERS)};\n"
        f"const ONE = {D(j('ONE.json'))};\n")

html = open(os.path.join(HERE, 'shell.html')).read().replace('__DATA__', blob)
assert '__DATA__' not in html, '템플릿 자리표시자가 치환되지 않았다'

# 아티팩트용 파일은 <title> 부터 시작하는 조각이다(게시할 때 Claude 가 껍데기를 씌운다).
# 웹서버에 그대로 올리면 quirks mode·모바일 뷰포트·한글 인코딩이 깨진다. 여기서 감싼다.
head, body = html.split('</style>', 1)
page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
{head}</style>
<style>html{{-webkit-text-size-adjust:100%}} body{{margin:0}} img{{max-width:100%}} [hidden]{{display:none !important}}</style>
</head>
<body>
{body}
</body>
</html>
"""
open('_plain.html', 'w').write(page)

# 갱신 버튼이 폴링하는 파일. 개인정보 없이 스냅샷 시각만 담는다(암호화하지 않는다).
os.makedirs('dist', exist_ok=True)
meta = j('META.json')
# buildId 는 새로고침 URL 의 캐시 무력화 값으로도 쓰인다.
# 같은 분(分)에 두 번 돌아 fetchedAt 이 같아도 run_id 가 다르면 새 페이지를 받는다.
json.dump({'fetchedAt': meta['fetchedAt'],
           'buildId': os.environ.get('GITHUB_RUN_ID', 'local')},
          open('dist/status.json', 'w'), ensure_ascii=False)

print(f'_plain.html {len(page.encode())/1024:.0f}KB · status.json {meta["fetchedAt"]}')
