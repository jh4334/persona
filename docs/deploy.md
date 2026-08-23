# 배포 가이드

## 먼저 — 어디에 올릴 것인가

이 앱은 **수업이 진행되는 동안 상태를 들고 있는 서버**다. 그래서 호스팅 방식에
따라 되는 것과 안 되는 것이 갈린다.

| | Vercel (서버리스) | 컨테이너 호스트 |
|---|---|---|
| mock 백엔드 (연습용) | ✅ | ✅ |
| anthropic 백엔드 | ⚠️ 턴이 제한 시간 안에 끝나야 | ✅ |
| **codex 백엔드** | **❌ 불가** | ✅ |
| 로컬 디스크 저장 | ❌ (Supabase 필수) | ✅ |
| 턴 최대 시간 | 60초(Hobby) / 300초(Pro) | 제한 없음 |
| 비용 | 무료 시작 | 대개 유료 |

**codex가 안 되는 이유**: codex 백엔드는 `codex exec`라는 CLI를 하위 프로세스로
띄운다. 서버리스 런타임에는 그 실행 파일도, `codex login` 상태도 없다. 서버는
이 사실을 알고 서버리스에서 `codex`를 아예 선택지에서 뺀다.

> **판단 기준**: mock으로 연습·시연만 한다면 Vercel이 간편하다.
> 실제 AI 반응(codex/anthropic)으로 40분 수업을 돌릴 거면 컨테이너 호스트를 권한다.

---

# A. Vercel 배포

## 0. Supabase 먼저 (필수)

**서버리스에서는 Supabase 없이 아무것도 저장되지 않는다.** 매 요청이 다른
인스턴스일 수 있고 로컬 디스크가 남지 않기 때문에, 서버는 서버리스를 감지하면
디스크 저장을 아예 끈다 (써 놓고 "저장됐다"고 믿었다가 다음 요청에서 사라지는
것이 가장 나쁜 실패라서).

[docs/supabase_setup.md](supabase_setup.md)를 먼저 끝내야 한다:

1. SQL Editor에 `db/schema.sql` 전체 붙여넣고 Run (테이블 3개 + RLS)
2. Authentication → Email provider 켜기
3. Project Settings → API 에서 `anon` 키와 `JWT Secret` 복사

## 1. 프로젝트 연결

```bash
npm i -g vercel
vercel login
vercel link          # 이 저장소에서
```

## 2. 환경변수

```bash
vercel env add SUPABASE_URL          # https://<project>.supabase.co
vercel env add SUPABASE_ANON_KEY     # anon (public) 키
vercel env add SUPABASE_JWT_SECRET   # JWT Secret
```

`service_role` 키는 **넣지 않는다** — 로그인을 켜면 사용자 JWT로 충분하다
(RLS 모드). Vercel은 `VERCEL=1`을 자동으로 넣어 주므로 서버리스 모드는
따로 켤 필요가 없다.

## 3. 배포

```bash
vercel --prod
```

## 4. 배포 후 확인

```bash
curl -s https://<앱>.vercel.app/healthz
```

```jsonc
{
  "mode": "serverless",              // ← 서버리스로 인식됨
  "store": "supabase",               // ← "none" 이면 Supabase 미설정 (치명적)
  "auth": "required",                // ← "open" 이면 아무나 들어옴
  "remote_auth": "RLS(사용자 토큰)",  // ← "service_role" 이면 키를 뺄 것
  "backends": ["mock", "anthropic"]  // ← codex는 여기 없는 게 정상
}
```

`store`가 `none`이면 **수업이 턴마다 사라진다.** 환경변수를 다시 확인할 것.

## 5. 로그인 리다이렉트 주소 등록

Supabase 대시보드 → Authentication → URL Configuration → Redirect URLs 에
배포된 주소를 넣는다. 안 하면 로그인 메일의 링크가 앱으로 돌아오지 못한다.

```
https://<앱>.vercel.app
```

미리보기 배포까지 쓰려면 `https://<앱>-*.vercel.app` 패턴도 함께 등록한다.

## Vercel에서 알아 둘 것

- **턴 시간**: `vercel.json`의 `maxDuration`이 60초다. Hobby 플랜의 상한이며,
  Pro라면 300까지 올릴 수 있다. anthropic 백엔드로 학급이 크면 60초를 넘길 수
  있으니, 넘긴다면 Pro로 올리거나 학급을 줄인다.
- **콜드 스타트**: 한동안 요청이 없으면 첫 턴이 몇 초 느리다.
- **수업 이어하기**: 인스턴스가 바뀌어도 이어진다. 세션이 메모리에 없으면
  Supabase에서 그 사용자의 토큰으로 하나만 되살린다(지연 복구).
- **저장 실패 시**: 턴 응답에 "이번 턴을 저장하지 못했습니다" 안내가 나온다.
  서버리스에서는 이 턴이 곧 유실되므로, 그때 전사를 내려받아야 한다.

---

# B. 컨테이너 호스트 배포

Railway · Render · Fly.io · Cloud Run · 학교 서버 등, **프로세스가 계속 살아
있는** 곳이면 제약 없이 전부 동작한다.

```bash
docker build -t boineun-gyosil .

docker run -p 8000:8000 \
  -e SUPABASE_URL=https://<project>.supabase.co \
  -e SUPABASE_ANON_KEY=<anon 키> \
  -e SUPABASE_JWT_SECRET=<JWT Secret> \
  -v $(pwd)/reports:/app/reports \
  boineun-gyosil
```

- Supabase 없이도 동작한다 (로컬 디스크에 저장). 다만 컨테이너를 재배포하면
  사라지므로 볼륨을 붙이거나 Supabase를 쓴다.
- codex 백엔드를 쓰려면 이미지에 codex CLI를 넣고 로그인 상태를 마운트해야 한다.
  기본 이미지에는 들어 있지 않다.
- `PORT` 환경변수를 읽으므로 대부분의 PaaS에 그대로 올라간다.

---

# C. CI

`.github/workflows/ci.yml` 이 push마다 회귀 24개 스위트를 돌리고 컨테이너
이미지 빌드까지 확인한다. Playwright용 크로미엄은 CI가 직접 설치한다.

로컬에서는:

```bash
python tests/regression/run_all.py     # → ALL REGRESSION PASS
```

---

# 배포 전 최종 확인

- [ ] `db/schema.sql` 적용 (테이블 3개 + RLS 정책)
- [ ] Authentication → Email provider 켜짐, Redirect URLs 등록
- [ ] SMTP 연결 (기본 발송기는 시간당 2~3통 제한)
- [ ] `/healthz` → `"auth":"required"`, `"store"`가 `none`이 아님
- [ ] `service_role` 키가 환경변수에 **없음** (`remote_auth`가 RLS인지 확인)
- [ ] 실제로 로그인 → 학급 만들기 → 수업 1턴 → `/종료` → [지난 수업 기록]까지 한 바퀴
