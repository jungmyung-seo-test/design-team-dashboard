/**
 * shell.html 을 고친 뒤, 실제로 화면이 그려지는지 로컬에서 확인한다.
 *
 * 배포된 보드에서 데이터 상수만 빼내 지금 작업 중인 shell.html 에 넣고,
 * 브라우저로 열어볼 수 있는 파일을 만든다. 지라 조회도 CI 도 필요 없고,
 * Node 내장 모듈만 쓰므로 설치할 것도 없다.
 *
 *   BOARD_PASSWORD='비밀번호' node ci/rendertest.mjs
 *   → _rendertest.html
 *
 * 왜 필요한가: 문법 검사와 문자열 세기로는 못 잡는 사고가 있다. JS 템플릿
 * 리터럴 안에 HTML 주석(<!-- -->)을 넣으면 ${} 가 그대로 평가돼
 * ReferenceError 가 나는데 `node --check` 는 통과한다. 실제로 이것 때문에
 * 보드가 통째로 빈 적이 있다.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { pbkdf2Sync, createDecipheriv } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE  = dirname(fileURLToPath(import.meta.url));
const ROOT  = dirname(HERE);
const SHELL = join(HERE, "build", "shell.html");
const OUT   = join(ROOT, "_rendertest.html");
const BOARD = process.env.BOARD_URL
  || "https://jungmyung-seo-test.github.io/design-team-dashboard/";
const CONSTS = ["TEAM", "LOAD", "META", "DESIGN", "ACCT", "JIRA", "MANAGERS", "ONE"];

const die = m => { console.error(m); process.exit(1); };

if (typeof fetch !== "function") die("Node 18 이상이 필요합니다 (현재 " + process.version + ")");

const pw = process.env.BOARD_PASSWORD;
if (!pw) die("BOARD_PASSWORD 환경변수가 필요합니다 (팀에 공유된 보드 비밀번호)");

console.log(`배포본 내려받는 중… ${BOARD}`);
const res = await fetch(BOARD, { headers: { "User-Agent": "rendertest" } });
if (!res.ok) die(`받기 실패: HTTP ${res.status}`);
const locked = await res.text();

const grab = re => { const m = locked.match(re); return m && m[1]; };
if (!grab(/SALT="([^"]+)"/)) die("잠금 페이지가 아닙니다 — BOARD_URL 을 확인하세요");

let plain;
try {
  const salt = Buffer.from(grab(/SALT="([^"]+)"/), "base64");
  const iv   = Buffer.from(grab(/IV="([^"]+)"/), "base64");
  const all  = Buffer.from(grab(/CT="([^"]+)"/), "base64");
  const iter = parseInt(grab(/ITER=(\d+)/), 10);
  const key  = pbkdf2Sync(pw, salt, iter, 32, "sha256");
  const d    = createDecipheriv("aes-256-gcm", key, iv);
  d.setAuthTag(all.subarray(all.length - 16));
  plain = Buffer.concat([d.update(all.subarray(0, all.length - 16)), d.final()]).toString("utf8");
} catch {
  die("복호화 실패 — 비밀번호를 확인하세요");
}

const blob = CONSTS.map(k => {
  const m = plain.match(new RegExp(`^const ${k} = .*;$`, "m"));
  if (!m) die(`배포본에서 ${k} 를 못 찾았습니다`);
  return m[0];
}).join("\n") + "\n";

const shell = readFileSync(SHELL, "utf8");
const html = shell.replace("__DATA__", () => blob);
if (html.includes("__DATA__")) die("shell.html 의 __DATA__ 자리표시자를 못 찾았습니다");

const [head, body] = html.split(/<\/style>(.*)/s).slice(0, 2);
writeFileSync(OUT,
  `<!doctype html><html lang="ko"><head><meta charset="utf-8">` +
  `<meta name="viewport" content="width=device-width, initial-scale=1">` +
  `${head}</style></head><body>${body}</body></html>`);

const meta = JSON.parse(plain.match(/^const META = (.*);$/m)[1]);
const team = JSON.parse(plain.match(/^const TEAM = (.*);$/m)[1]);
console.log(`\n${OUT}`);
console.log(`  데이터 스냅샷 ${meta.fetchedAt} · 인원 ${team.length}명`);
console.log(`\n브라우저로 열어 확인하세요:\n  open "${OUT}"`);
console.log("  · 카드가 인원수만큼 보이는가");
console.log("  · 카드를 눌렀을 때 상세 패널이 열리는가");
console.log("  · 개발자도구 콘솔에 오류가 없는가");
