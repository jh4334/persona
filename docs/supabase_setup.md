# Supabase 연결 가이드 (v0.6 1단계 — 세션 스냅샷)

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

## 아직 안 된 것 (2단계)

- **인증.** 지금도 URL을 아는 누구나 세션을 만들 수 있다. `user_id`는 null로
  들어간다. 공개 인터넷 배포는 여전히 안 된다.
- 학급·전사·리포트의 Supabase 저장 (지금은 세션 스냅샷만).
- 브라우저에서 Supabase Auth 로그인 → JWT → `anon` 키 + RLS 경로.
