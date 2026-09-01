# design-team-dashboard

무신사 Product Design 조직(디자인실) 역할·업무량 보드.

공개 URL — `https://jungmyung-seo-test.github.io/design-team-dashboard/`

## 어떻게 도는가

이 리포에는 **보드 파일이 없다.** 소스만 있고, 결과물은 GitHub Actions 가 만들어
Pages 로 바로 배포한다. 커밋하지 않으므로 실명·티켓 제목이 리포 히스토리에 쌓이지 않는다.

```
① 담당자가 지라에서 티켓 업데이트
② 보드에서 [지금 갱신] 클릭
        ↓ POST
③ Cloudflare Worker            ← GitHub 토큰을 여기서만 쥔다
        ↓ workflow_dispatch
④ GitHub Actions (refresh.yml) ← 지라 토큰을 여기서만 쥔다
   fetch → agg → one → mk → verify → lock → Pages 배포
        ↓
⑤ 페이지가 status.json 을 확인하다 갱신되면 저절로 새 보드를 연다
```

버튼 클릭부터 새 보드가 서빙될 때까지 **약 30초**다(지라 조회 17초 + 배포).
버튼 외에 **매일 09:00 KST(평일)** 스케줄로도 돈다.

브라우저는 지라를 직접 부르지 않는다. 그러면 토큰이 페이지에 박히고 CORS 도 막힌다.
"갱신해 줘" 한 마디만 Worker 에 보내고, 실제 조회는 Actions 안에서 일어난다.

## 구성

| 경로 | 설명 |
|---|---|
| `ci/build/fetch.py` | 지라 REST 조회 → `raw/{work,cont,one}.json` |
| `ci/build/agg.py` · `one.py` | 집계 → `LOAD/DESIGN/META/ACCT/ONE.json` |
| `ci/build/mk.py` | `shell.html` 템플릿에 데이터 주입 → 평문 보드 + `status.json` |
| `ci/build/verify.py` | **게시 전 검증 게이트.** 막히면 배포하지 않는다 |
| `ci/build/lock.py` | AES-256-GCM 암호화 (PBKDF2-SHA256 31만 회) |
| `ci/worker/` | 버튼이 부르는 Cloudflare Worker |
| `ci/SETUP.md` | 설치·시크릿 등록 절차 |

`verify.py` 는 매직 넘버를 쓰지 않는다. 탭 수와 뷰 섹션 수가 **서로 맞는지**를 본다.
예전에 "탭 3개"라는 고정값을 검사하다가 구조 변경 후 매번 게시가 거부돼 보드가 5일간
멈춘 적이 있어서다.

## 설정값

값은 여기에 적지 않는다. 이름만 적는다. 자세한 절차는 `ci/SETUP.md`.

| 종류 | 이름 |
|---|---|
| Secrets | `JIRA_EMAIL` · `JIRA_TOKEN` · `BOARD_PASSWORD` · `BOARD_CONFIG` · `REFRESH_KEY`(선택) |
| Variables | `REFRESH_API` |

명부·소속·ONE 그룹·지라 조회 조건은 전부 `BOARD_CONFIG` 시크릿 안에 있다.
**인원이 바뀌면 그 시크릿만 고친다. 코드는 건드리지 않는다.**

## 비밀번호

GitHub Pages 에는 인증 기능이 없다(접근 제어되는 Private Pages 는 Enterprise Cloud 전용).
그래서 페이지 자체를 암호화해 올리고 브라우저에서 푼다.

- 팀에 공유된 비밀번호 하나로 모두가 같은 URL 을 연다
- 한 번 열면 **같은 탭에서는 새로고침해도 다시 묻지 않는다**(탭을 닫으면 초기화)
- **비밀번호는 이 리포에 적지 않는다.** 링크와 다른 경로로 공유한다
- 바꾸려면 `BOARD_PASSWORD` 시크릿을 고치고 refresh 를 한 번 돌린다

## 알아둘 것

- **리포 히스토리에는 예전에 커밋했던 잠금본이 남아 있다.** 지금 비밀번호로 열리므로,
  비밀번호가 새면 그 파일들도 함께 열린다. 완전히 지우려면 히스토리를 다시 쓰거나
  리포를 지우고 새로 만들어야 한다
- **Pages 사이트는 리포가 private 이어도 인터넷 전체에 공개다.** 잠금 화면이 유일한 접근 통제다
- Actions 로그도 공개다. 그래서 빌드 스크립트는 실명을 가려서 찍는다(`김*아`)
- 보드에는 구성원 실명 26명 · 개인별 업무량과 부하 판정 · 사내 지라 이슈 키와 제목이 들어 있다.
  **사외 공유 금지**
