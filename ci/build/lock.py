#!/usr/bin/env python3
"""평문 보드를 비밀번호로 잠근 단일 HTML 로 만든다.

GitHub Pages 에는 비밀번호 기능이 없다. 그래서 페이지 자체를 AES-GCM 으로 암호화해
올리고 브라우저에서 풀도록 한다. 서버에 있는 것은 암호문이라 비밀번호를 모르면
소스를 봐도 내용이 나오지 않는다.

  python3 lock.py <평문.html> <출력.html>      # 비밀번호는 BOARD_PASSWORD 환경변수
"""
import base64, hashlib, os, secrets, sys

ITER = 310000                      # PBKDF2-SHA256 반복 (OWASP 권장선)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    sys.exit('pip install cryptography 먼저 실행하세요')


def main(src, out, pw):
    data = open(src, 'rb').read()
    salt = secrets.token_bytes(16)
    iv   = secrets.token_bytes(12)
    key  = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, ITER, 32)
    ct   = AESGCM(key).encrypt(iv, data, None)
    b64  = lambda b: base64.b64encode(b).decode()

    page = (GATE.replace('__SALT__', b64(salt)).replace('__IV__', b64(iv))
                .replace('__CT__', b64(ct)).replace('__ITER__', str(ITER)))
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'w').write(page)
    print(f'{out}  {len(page)/1024:.0f}KB  (원본 {len(data)/1024:.0f}KB)')


GATE = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>BiznP Product Design</title>
<style>
:root{--bg:#f4f4f4; --surface:#fff; --ink:#1c1c1e; --ink-2:#6b6b70; --sep:rgba(0,0,0,.10);
  --field:#fff; --accent:#007AFF; --err:#C6362C}
@media (prefers-color-scheme:dark){
  :root{--bg:#000; --surface:#1c1c1e; --ink:#f2f2f7; --ink-2:#98989e; --sep:rgba(255,255,255,.14);
    --field:#2c2c2e; --accent:#0A84FF; --err:#FF6961}
}
*{box-sizing:border-box}
body{margin:0; min-height:100vh; display:grid; place-items:center; padding:24px;
  background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR",
    "Malgun Gothic",Arial,sans-serif; font-size:15px; letter-spacing:-.01em}
form{width:100%; max-width:340px; background:var(--surface); border-radius:14px;
  padding:26px 24px; box-shadow:0 1px 2px rgba(0,0,0,.06), 0 8px 30px rgba(0,0,0,.08)}
h1{margin:0 0 4px; font-size:19px; font-weight:700; letter-spacing:-.02em}
p{margin:0 0 18px; font-size:13px; color:var(--ink-2); line-height:1.5}
label{display:block; font-size:12px; color:var(--ink-2); margin-bottom:6px}
input{width:100%; padding:10px 12px; font-size:15px; font-family:inherit; color:var(--ink);
  background:var(--field); border:1px solid var(--sep); border-radius:9px; outline:none}
input:focus{border-color:var(--accent); box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}
button{width:100%; margin-top:12px; padding:11px; font-size:15px; font-weight:600; font-family:inherit;
  color:#fff; background:var(--accent); border:0; border-radius:9px; cursor:pointer}
button[disabled]{opacity:.55; cursor:default}
.msg{margin-top:12px; font-size:12.5px; min-height:1.2em; color:var(--err)}
.msg.wait{color:var(--ink-2)}
</style>
</head>
<body>
<form id="f" autocomplete="on">
  <h1>BiznP Product Design</h1>
  <p>디자인실 역할·업무량 보드입니다. 팀에 공유된 비밀번호를 입력해 주세요.</p>
  <label for="pw">비밀번호</label>
  <input id="pw" type="password" autocomplete="current-password" autofocus>
  <button id="go" type="submit">열기</button>
  <div class="msg" id="msg"></div>
</form>
<script>
const SALT="__SALT__", IV="__IV__", CT="__CT__", ITER=__ITER__, KEY="pdboard.pw";
const b=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
const msg=document.getElementById("msg"), go=document.getElementById("go");

async function unlock(pw){
  const enc=new TextEncoder();
  const base=await crypto.subtle.importKey("raw",enc.encode(pw),"PBKDF2",false,["deriveKey"]);
  const key=await crypto.subtle.deriveKey(
    {name:"PBKDF2",salt:b(SALT),iterations:ITER,hash:"SHA-256"},
    base,{name:"AES-GCM",length:256},false,["decrypt"]);
  const out=await crypto.subtle.decrypt({name:"AES-GCM",iv:b(IV)},key,b(CT));
  return new TextDecoder().decode(out);
}
function show(html){
  document.open(); document.write(html); document.close();
}
async function attempt(pw,remember){
  go.disabled=true; msg.className="msg wait"; msg.textContent="여는 중…";
  try{
    const html=await unlock(pw);
    if(remember){ try{ sessionStorage.setItem(KEY,pw); }catch(e){} }
    show(html);
  }catch(e){
    try{ sessionStorage.removeItem(KEY); }catch(_){}
    go.disabled=false; msg.className="msg"; msg.textContent="비밀번호가 맞지 않습니다.";
    document.getElementById("pw").select();
  }
}
document.getElementById("f").onsubmit=e=>{
  e.preventDefault();
  const pw=document.getElementById("pw").value;
  if(pw) attempt(pw,true);
};
/* 같은 탭에서 새로고침하면 다시 묻지 않는다. 탭을 닫으면 사라진다.
   갱신 버튼이 페이지를 새로고침해도 비밀번호를 다시 묻지 않는 것이 이 덕분이다. */
(async()=>{ let s=null; try{ s=sessionStorage.getItem(KEY); }catch(e){}
  if(s) attempt(s,false); })();
</script>
</body>
</html>
'''

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    password = os.environ.get('BOARD_PASSWORD')
    if not password:
        sys.exit('BOARD_PASSWORD 환경변수가 비어 있습니다')
    main(sys.argv[1], sys.argv[2], password)
