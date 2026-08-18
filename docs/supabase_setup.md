# Supabase 연결 가이드 (v0.6)

1단계 세션 스냅샷 · 2단계 로그인 · 3단계 내 학급 만들기.

---

# 1단계 — 세션 스냅샷

## 왜 필요한가

지금 세션 스냅샷은 서버 로컬 디스크(`.sessions/`)에만 남는다. 같은 PC에서
서버를 껐다 켜는 것은 이미 복구되지만(11차), **컨테이너를 재배포하거나 서버를
여러 대로 늘리면 진행 중 수업이 사라진다.** Supabase에 함께 기록해 두면 서버가
바뀌어도 수업이 살아남는다.

디스크 기록은 그대로 유지된다. 둘 다 쓰고, 복구할 때 더 최근 스냅샷을 고른다.
Supabase가 죽어도 수업은 끊기지 않는다 (경고 로그만 남고 디스크로 계속 동작).

## 1. 스키마 적용

Supabase 대시보드 → **SQL Editor** → `db/schema.sql` 내용을 붙여넣고 **Run**.
여러 번 실행해도 안전하다.

만들어지는 것:
- `stage_sessions` 테이블 (id, user_id, class_name, saved_at, payload, updated_at)
- `saved_at desc` 인덱스 — 기동 시 "TTL 안쪽 최신순" 조회용
- RLS 활성화 + `authenticated` 사용자 본인 행만 접근하는 정책
- `purge_stale_sessions(keep_days)` — 오래된 스냅샷 정리 함수

## 2. 키 확인

대시보드 → **Project Settings → API**:

| 키 | 용도 | 취급 |
|---|---|---|
| `anon` (public) | 브라우저용 | 공개돼도 됨. RLS가 막는다. **1단계에서는 안 씀** |
| `service_role` | 서버용 | **절대 공개 금지.** RLS를 우회한다 |

1단계에서 서버는 `service_role` 키를 쓴다. 아직 로그인이 없어 `user_id`를
채울 주체가 없기 때문이다. 인증이 붙는 2단계에서 사용자 JWT + `anon` 키로
바꾸면 `service_role` 키 자체가 필요 없어진다.

> ⚠️ **`service_role` 키를 채팅·이슈·커밋에 붙여넣지 말 것.** 아래처럼 환경변수로만
> 전달한다. `.env`는 이미 `.gitignore`에 있다.

## 3. 서버에 환경변수 설정

```bash
export SUPABASE_URL=https://obmlsijdaknzwktplklr.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<대시보드에서 복사한 service_role 키>

PYTHONPATH=src python -m classroom_sim.web --port 8000
```

`.env` 파일로 관리해도 된다 (git에 올라가지 않는다):

```bash
# .env
SUPABASE_URL=https://obmlsijdaknzwktplklr.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
```

인식하는 변수 이름:

| 변수 | 필수 | 기본값 |
|---|---|---|
| `SUPABASE_URL` | ✅ | — (없으면 디스크만 사용) |
| `SUPABASE_KEY` / `SUPABASE_SERVICE_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — |
| `SUPABASE_TABLE` | | `stage_sessions` |

## 4. 연결 확인

```bash
curl -s http://127.0.0.1:8000/healthz
```

```jsonc
{"status":"ok", "sessions":0, "store":"disk+supabase"}   // ← 연결됨
{"status":"ok", "sessions":0, "store":"disk"}            // ← 환경변수 미인식
```

`store`가 `disk`로 나오면 환경변수가 서버 프로세스에 전달되지 않은 것이다.
URL에 `https://`를 빠뜨린 경우에도 무시되며, 기동 로그에 경고가 남는다.

## 5. 동작 확인 (서버 이전 시나리오)

1. 수업을 시작하고 몇 턴 진행한다.
2. Supabase 대시보드 → **Table Editor → stage_sessions** 에 행이 생기고
   턴마다 `payload`가 갱신되는지 본다 (행이 *쌓이지* 않고 갱신돼야 정상 — upsert).
3. 서버를 끄고 **`.sessions/` 디렉터리를 통째로 지운 뒤** 다시 켠다.
4. 브라우저를 새로고침하면 '이어하기'로 같은 수업이 재개된다.

3번이 로컬 디스크 없이 되면 서버를 갈아끼워도 살아남는다는 뜻이다.
회귀 테스트 `tests/regression/test_cycle21.py`가 가짜 PostgREST로 이 시나리오를
자동 검증한다 (실제 Supabase 연결·키 불필요).

## 6. 보관 기간 정리 (선택)

무료 티어 용량을 지키려면 대시보드 → **Database → Cron**에서 예약한다:

```sql
select cron.schedule('purge-stage-sessions', '0 18 * * *',
                     $$select public.purge_stale_sessions(7)$$);
```

서버는 TTL(3시간)이 지난 스냅샷을 조회에서 제외할 뿐 삭제하지 않으므로,
정리하지 않으면 행이 계속 쌓인다.

---

# 2단계 — 로그인 (Supabase Auth)

인증을 켜면 **로그인한 교사만** 수업을 만들 수 있고, **자기 수업만** 볼 수 있다.
공개 인터넷 배포를 막고 있던 최대 리스크가 여기서 해소된다.

## 동작 방식

```
브라우저 ──(이메일 로그인)──> Supabase Auth        ← anon 키만 사용 (공개해도 되는 키)
   │  JWT
   ▼
우리 서버 ──(토큰 검증)──> 사용자 확인 → 세션 소유권 검사
```

브라우저는 **인증에만** Supabase를 직접 부른다. 학급·세션·전사는 전부 우리 서버를
거치므로 브라우저에 나가는 것은 anon 키뿐이다.

## 1. 로그인 방식 켜기

대시보드 → **Authentication → Sign In / Providers → Email**

- **Enable Email provider** 켜기
- **Confirm email** 켜 둔 채로 두면 첫 로그인 시 확인 메일이 간다
- 비밀번호 없이 쓰므로 **Enable Email OTP**(또는 Magic Link)가 켜져 있으면 된다

## 2. 돌아올 주소 등록

대시보드 → **Authentication → URL Configuration → Redirect URLs** 에 서비스 주소를
넣는다. 등록하지 않으면 메일의 링크를 눌러도 앱으로 돌아오지 못한다.

```
http://localhost:8000
http://192.168.0.10:8000      ← 휴대폰에서 LAN으로 접속한다면 그 주소도
```

> IP 주소로 접속하는 환경에서는 링크가 잘 안 열린다. 로그인 화면에는 **6자리 코드**
> 입력란도 있으니 그쪽을 쓰면 된다. 코드가 메일에 나오게 하려면
> **Authentication → Emails → Magic Link** 템플릿에 `{{ .Token }}` 을 넣는다.

## 3. 메일 발송 설정 (중요)

Supabase 기본 메일 발송기는 **시간당 2~3통**으로 제한된 테스트용이다. 본인 확인
정도는 되지만 동료 교사들과 나눠 쓰려면 **Authentication → Emails → SMTP Settings**
에서 직접 쓰는 SMTP(예: 학교 계정, Gmail 앱 비밀번호, Resend 등)를 연결해야 한다.

## 4. 키 확인과 환경변수

대시보드 → **Project Settings → API**:

| 값 | 어디서 쓰나 |
|---|---|
| `anon` (public) | 브라우저 로그인 화면. **공개돼도 안전** |
| `JWT Secret` | 서버가 토큰 서명을 직접 검증 (Settings → API → JWT Settings) |
| `service_role` | 서버의 스냅샷 저장 (1단계) |

```bash
export SUPABASE_URL=https://obmlsijdaknzwktplklr.supabase.co
export SUPABASE_ANON_KEY=<anon 키>
export SUPABASE_JWT_SECRET=<JWT Secret>          # 선택 — 없으면 원격 확인으로 동작
export SUPABASE_SERVICE_ROLE_KEY=<service_role>  # 1단계 스냅샷 저장용

PYTHONPATH=src python -m classroom_sim.web --port 8000
```

| 변수 | 없으면 |
|---|---|
| `SUPABASE_ANON_KEY` | 로그인 화면이 Supabase를 부르지 못한다 (인증 비활성) |
| `SUPABASE_JWT_SECRET` | 토큰을 매번 Supabase에 물어본다(1분 캐시). 느릴 뿐 동작은 한다 |
| `AUTH_REQUIRED` | URL+ANON_KEY가 있으면 **자동으로 켜진다**. `0`으로 끌 수 있다 |

`SUPABASE_JWT_SECRET`이 있으면 서버가 서명을 직접 검증해 네트워크 왕복이 없다.
비대칭 키(ES256/RS256)를 쓰는 프로젝트는 시크릿으로 검증할 수 없으므로 자동으로
원격 확인으로 넘어간다 — 둘 다 설정해 두면 알아서 빠른 쪽을 쓴다.

## 5. 확인

```bash
curl -s http://127.0.0.1:8000/healthz          # → "auth":"required"
curl -s http://127.0.0.1:8000/api/classrooms   # → 401 (로그인 없이는 목록도 못 봄)
```

브라우저로 접속하면 셋업 화면 대신 **로그인 화면**이 먼저 뜬다. 이메일 입력 →
메일의 링크를 누르거나 6자리 코드 입력 → 셋업 화면 진입. 새로고침해도 로그인이
유지되고, 셋업 화면 아래에 계정과 [로그아웃]이 표시된다.

## 6. 인증을 켰을 때 달라지는 것

- `/api/classrooms`·`/api/lessons`·`/api/sessions/*` 전부 로그인 필요
- 세션에 소유자가 기록되고, **남의 수업은 404**로 응답한다 (존재 여부까지 숨김)
- 세션 생성 속도 제한(10분당 10회)이 IP가 아니라 **사용자 기준**으로 바뀐다
- 스냅샷 행의 `user_id`가 채워져 `db/schema.sql`의 RLS 정책이 실제로 동작한다
- 서버를 재시작해도 소유권이 유지된다

전 과정을 `tests/regression/test_cycle22.py`가 가짜 Supabase Auth로 자동 검증한다
(실제 연결·키 불필요).

---

# 3단계 — 내 학급 만들기

지금까지 학급은 저장소의 `personas/*.json` 파일뿐이었다. 서버 파일을 직접 고칠 수
있는 사람만 자기 학급을 만들 수 있다는 뜻이라, 로그인이 붙은 뒤로는 말이 되지
않는다. 이제 교사가 화면에서 직접 학급을 만들고, 만든 사람에게만 보인다.

| 구분 | 어디에 | 누구에게 보이나 | 지울 수 있나 |
|---|---|---|---|
| **샘플 학급** | 저장소 `personas/*.json` | 모두 | ✗ (읽기 전용) |
| **내 학급** | Supabase 또는 `.classrooms/` | 만든 사람만 | ✓ |

## 설정

`db/schema.sql`을 다시 한 번 Run 하면 `classrooms` 테이블이 추가된다 (여러 번
실행해도 안전하다). 환경변수는 1단계와 같은 것을 쓴다 — 따로 더할 것이 없다.

`SUPABASE_URL`/`KEY`가 없으면 `.classrooms/` 디렉터리에 저장된다. 로그인 없이
혼자 쓸 때도 학급 만들기가 그대로 동작한다는 뜻이다.

> 세션 스냅샷과 달리 학급은 **이중 기록을 하지 않는다.** 스냅샷은 몇 시간이면
> 사라지는 사본이라 어느 쪽이 남아도 그만이지만, 학급은 교사가 만든 원본이다.
> 두 곳에 두면 서로 어긋났을 때 무엇이 맞는지 알 수 없다. 그래서 Supabase를
> 설정하면 학급은 Supabase에만 저장되고, 그 전에 `.classrooms/`에 만들어 둔
> 학급은 목록에 나오지 않는다 (파일은 남아 있으니 다시 붙여넣으면 된다).

## 쓰는 법

셋업 화면의 **[+ 내 학급 만들기]** → 학급 JSON을 붙여넣거나 파일 선택 → [저장].
형식이 틀리면 어디가 문제인지 한국어로 짚어 준다 (`학생 S03에 name(이름)이
없습니다` 처럼). 저장하면 목록 맨 위 "내 학급" 묶음에 들어가고 바로 선택된다.

형식은 `personas/class_6_3.json`과 같다. 최소한 이 정도면 된다:

```json
{
  "class_name": "행복초 5학년 2반",
  "grade": "초등학교 5학년",
  "students": [
    { "id": "S01", "name": "김하늘", "achievement_level": "상" },
    { "id": "S02", "name": "박서준", "achievement_level": "중" }
  ]
}
```

속성을 더 넣을수록 반응이 구체적으로 나온다 — 전체 목록은
[docs/dimension_reference.md](dimension_reference.md) 참고.

## 제한

| 항목 | 값 |
|---|---|
| 한 사람당 학급 수 | 50개 |
| 학급 파일 크기 | 512KB |
| 학급 인원 | 40명 |

## 알아 둘 것

- 수업 중에 그 학급을 지워도 **진행 중이던 수업은 끊기지 않는다.** 스냅샷에
  학급 원본을 함께 담아 두기 때문에, 서버를 재시작해도 시작할 때의 학생들로
  이어진다.
- 학급을 고쳐도 이미 진행 중인 수업에는 반영되지 않는다 (같은 이유).
- 실제 학생의 실명·진단명·가정사를 넣지 말 것. 가상 페르소나나 익명화한 특성만
  쓰는 것을 권한다.

## 아직 안 된 것 (다음)

- 전사·리포트의 Supabase 저장 (지금은 서버 파일 `reports/stage/`에만)
- 학급을 폼으로 만드는 UI (지금은 JSON 붙여넣기 — 로드맵 v0.4의 "페르소나 입력 UI")
- 서버가 스냅샷·학급 저장에 아직 `service_role` 키를 쓴다. 기동 시 전체 세션을
  복구해야 해서인데, 사용자별 지연 복구로 바꾸면 이 키를 없앨 수 있다.
- ChatGPT 앱(MCP) 경로 — `docs/specs/v0.6_chatgpt_app.md`
