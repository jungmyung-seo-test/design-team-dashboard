# 갱신 버튼 설치 가이드

보드의 **`지금 갱신`** 버튼이 도는 데 필요한 설정을 순서대로 적었다.
한 번만 하면 되고, 이후에는 버튼과 매일 09:00 스케줄이 알아서 돈다.

```
① 담당자가 지라에서 티켓 업데이트
② 보드에서 [지금 갱신] 클릭
        ↓  POST
③ Cloudflare Worker      ← GitHub 토큰을 여기서만 쥔다
        ↓  workflow_dispatch
④ GitHub Actions         ← 지라 토큰을 여기서만 쥔다
   fetch → agg → one → mk → verify → lock → Pages 배포
        ↓
⑤ 페이지가 status.json 을 폴링하다 시각이 바뀌면 자동으로 새 보드를 연다
```

**지라 토큰은 ④ 안에만 있다.** 페이지에도 Worker 에도 들어가지 않는다.
브라우저는 "갱신해 줘"라고 말할 뿐 지라를 직접 부르지 않는다.

---

## 0. 리포에 올릴 것 / 올리면 안 되는 것

올린다 — 개인정보가 하나도 없다.

```
.github/workflows/refresh.yml
ci/build/{fetch,agg,one,mk,verify,lock}.py
ci/build/shell.html
ci/worker/{index.js,wrangler.toml}
ci/BOARD_CONFIG.example.json
ci/SETUP.md
.gitignore
```

**절대 올리지 않는다.** `.gitignore` 에 이미 들어 있지만 한 번 더 확인한다.

| 파일 | 이유 |
|---|---|
| `ci/BOARD_CONFIG.json` | 실명 26명 · 지라 그룹 id |
| `pd/` 전체 · `site/` · `site-locked/` | 실명 · 티켓 제목 |
| `raw/` · `dist/` · 루트의 `*.json` | 빌드 중간 산출물 |

리포가 **public** 이면 Actions 로그도 공개다. 그래서 스크립트는 기본적으로 실명을
가려서 찍는다(`김*아`). 확인이 필요하면 리포 변수 `BOARD_VERBOSE=1` 로 잠깐 켠다 —
**public 리포에서는 켜지 않는다.**

---

## 1. Pages 배포 방식을 바꾼다

리포 → **Settings → Pages → Build and deployment → Source** 를
`Deploy from a branch` 에서 **`GitHub Actions`** 로 바꾼다.

이렇게 하면 암호화된 보드를 리포에 커밋하지 않고 Pages 로 바로 올린다.
커밋 방식이면 공개 리포 히스토리에 암호문 스냅샷이 매일 쌓이고, 비밀번호가 한 번
새면 그날치가 아니라 **전체 히스토리가 열린다.** 그걸 피하기 위한 설정이다.

> URL 은 그대로 `https://jungmyung-seo-test.github.io/design-team-dashboard/` 다.

---

## 2. 지라 API 토큰

1. <https://id.atlassian.com/manage-profile/security/api-tokens> → **Create API token**
2. 라벨은 `pd-role-board` 정도로. 생성된 값을 복사한다

> 토큰은 **본인이 직접 등록한다.** 대화창이나 파일에 붙여넣지 않는다.

---

## 3. GitHub 시크릿·변수 등록

리포 → **Settings → Secrets and variables → Actions**

**Secrets** (New repository secret)

| 이름 | 값 |
|---|---|
| `JIRA_EMAIL` | 지라 계정 이메일 |
| `JIRA_TOKEN` | 2번에서 만든 토큰 |
| `BOARD_PASSWORD` | 팀에 공유한 보드 비밀번호 (값은 여기 적지 않는다) |
| `BOARD_CONFIG` | `ci/BOARD_CONFIG.json` **파일 내용 전체**를 그대로 붙여넣기 |

`BOARD_CONFIG` 는 명부·소속·ONE 그룹·지라 조회 조건이 모두 들어 있는 JSON 이다.
인원이 바뀌면 **이 시크릿만** 고치면 된다. 코드는 건드리지 않는다.

---

## 4. 첫 실행 (버튼 없이 확인)

리포 → **Actions → refresh → Run workflow**.
40초쯤 뒤 보드가 새로 배포되면 파이프라인이 정상이다.

성공하면 로그 끝에 이렇게 찍힌다.

```
인원 26명 · 티켓 283건 · 진행 중 40건 · 탭 3개 · 유형 3종 · 스냅샷 …
검증 통과
```

**검증에서 막히면 배포하지 않는다.** 반쪽짜리 보드로 덮어쓰는 것보다
옛 보드가 그대로 남는 편이 낫다는 판단이다.

---

## 5. Cloudflare Worker 배포

버튼이 부를 대상이다. 여기까지 해야 `지금 갱신` 이 화면에 나타난다.

### 5-1. GitHub 토큰 (Worker 전용)

<https://github.com/settings/personal-access-tokens> → **Fine-grained token**

- Repository access: **이 리포 하나만**
- Permissions → Repository permissions → **Actions: Read and write**
- 그 외 권한은 전부 No access

이 토큰으로 할 수 있는 일은 **이 리포의 기존 워크플로를 실행하는 것뿐**이다.
코드를 넣거나 내용을 읽을 수는 없다.

### 5-2. 배포

```bash
cd ci/worker
npx wrangler login
npx wrangler secret put GH_TOKEN     # 5-1 토큰을 여기서 붙여넣는다
npx wrangler deploy
```

`wrangler.toml` 의 `GH_REPO` · `ALLOWED_ORIGIN` 이 실제 값과 맞는지 확인한다.
배포가 끝나면 `https://pd-board-refresh.<계정>.workers.dev` 주소가 나온다.

### 5-3. 주소를 보드에 알려준다

리포 → Settings → Secrets and variables → Actions → **Variables** 탭 →
**New repository variable**

| 이름 | 값 |
|---|---|
| `REFRESH_API` | 5-2 에서 나온 Worker 주소 |

이 값이 없으면 버튼은 **숨은 채로 남는다.** 누를 대상이 없는 버튼을 보여주지
않기 위해서다. 값을 넣고 워크플로를 한 번 더 돌리면 그때부터 버튼이 보인다.

---

## 6. 확인

1. 보드를 연다 → 헤더에 `지금 갱신` 이 보인다
2. 지라에서 티켓 하나를 바꾼다
3. 버튼을 누른다 → `요청 중…` → `갱신 중…` → 1분 안에 저절로 새 보드가 뜬다
4. `데이터 갱신` 시각이 바뀌고, 바꾼 티켓이 반영돼 있다

비밀번호는 다시 묻지 않는다(같은 탭 `sessionStorage`).
26명이 동시에 눌러도 워크플로는 한 번만 돌고 나머지는 그 실행을 함께 기다린다.

---

## 7. 안 될 때

| 증상 | 확인할 것 |
|---|---|
| 버튼이 안 보인다 | `REFRESH_API` 변수가 비었거나, 등록 후 워크플로를 안 돌렸다 |
| `요청 실패` | Worker 주소 오타 · `ALLOWED_ORIGIN` 이 보드 Origin 과 다름 · `GH_TOKEN` 권한 |
| `시간 초과` | Actions 탭에서 실행이 실패했는지 본다. 검증에서 막혔을 가능성이 크다 |
| 시각도 내용도 그대로 | 배포가 성공했는지 확인. 성공했는데도 그대로면 브라우저 캐시 — 새로고침 URL 에 `?v=` 가 붙는지 본다 |
| `Jira 401` | `JIRA_EMAIL` / `JIRA_TOKEN` 조합. 토큰은 계정 이메일과 짝이어야 한다 |
| `0건 — JQL 또는 권한` | 지라 그룹 id 또는 계정 권한. 빈 결과로 보드를 덮어쓰지 않으려 일부러 멈춘 것이다 |
| 특정 인원 카드가 비었다 | 검증이 잡아낸다. `ACCT 매핑 누락` 경고를 본다 |

---

## 8. 남는 위험

- **비밀번호를 바꿔도 이전에 배포된 파일은 옛 비밀번호로 열린다.** Pages 직접 배포로
  바꾸면 히스토리에는 안 남지만, 이미 커밋된 과거 파일은 리포에 그대로 있다.
  필요하면 그 파일들을 지우고 히스토리를 정리한다
- **Worker 엔드포인트는 인증이 없다.** 주소를 아는 사람은 갱신을 실행시킬 수 있다.
  할 수 있는 일이 "보드를 다시 만든다"뿐이라 피해는 없지만, 실행 중이면 다시
  실행하지 않도록 Worker 가 막고 있다. 더 조이려면 Cloudflare Access 를 얹는다
- **GitHub Pages 는 리포가 private 이어도 사이트 자체는 인터넷 전체에 공개다.**
  잠금 화면이 유일한 접근 통제다
