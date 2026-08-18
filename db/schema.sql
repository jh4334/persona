-- 보이는 교실 — Supabase 스키마
--
-- 적용 방법: Supabase 대시보드 → SQL Editor → 이 파일 내용을 붙여넣고 Run.
-- 여러 번 실행해도 안전하다 (전부 if not exists / or replace).
--
-- 세션 스냅샷(stage_sessions)과 교사가 만든 학급(classrooms)을 담는다.
-- 전사·리포트는 아직 서버 파일로만 남는다.

-- ---------------------------------------------------------------------------
-- 세션 스냅샷
-- ---------------------------------------------------------------------------

create table if not exists public.stage_sessions (
    id          text primary key,                    -- 서버가 만드는 12자리 세션 id
    user_id     uuid references auth.users(id) on delete cascade,
                                                     -- 인증 도입 전에는 null (2단계에서 채움)
    class_name  text,                                -- 목록 화면용 표시 이름
    saved_at    double precision not null,           -- epoch 초 — TTL 필터에 사용
    payload     jsonb not null,                      -- {meta, saved_at, snapshot} 원본 그대로
    updated_at  timestamptz not null default now()
);

-- 기동 시 조회는 항상 "TTL 안쪽을 최신순으로" — 이 인덱스 하나면 충분하다.
create index if not exists stage_sessions_saved_at_idx
    on public.stage_sessions (saved_at desc);

create index if not exists stage_sessions_user_idx
    on public.stage_sessions (user_id, saved_at desc);

-- updated_at 자동 갱신
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;

drop trigger if exists stage_sessions_touch on public.stage_sessions;
create trigger stage_sessions_touch
    before update on public.stage_sessions
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 행 수준 보안 (RLS)
-- ---------------------------------------------------------------------------
--
-- RLS를 켜 두면 anon 키로는 아무것도 읽거나 쓸 수 없다. 서버는 service_role
-- 키를 쓰므로 RLS를 우회한다. 즉 "키가 새어도 프런트엔드에서는 남의 수업을
-- 못 본다"가 기본값이고, 2단계에서 사용자 로그인이 붙으면 아래 정책이 그대로
-- 사용자별 격리로 동작한다.

alter table public.stage_sessions enable row level security;

drop policy if exists "own sessions" on public.stage_sessions;
create policy "own sessions" on public.stage_sessions
    for all
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- anon(로그인 안 한 브라우저)에는 어떤 정책도 주지 않는다 → 전면 차단.

-- ---------------------------------------------------------------------------
-- 내 학급 (교사가 만든 학급 페르소나)
-- ---------------------------------------------------------------------------
--
-- 저장소의 `personas/*.json`은 모두에게 보이는 읽기 전용 샘플로 남고, 교사가
-- 직접 만든 학급만 여기 들어온다. 세션 스냅샷과 달리 이중 기록을 하지 않는다 —
-- 스냅샷은 몇 시간이면 사라지는 사본이지만 학급은 교사가 만든 원본이라,
-- 두 곳에 두면 어긋났을 때 무엇이 맞는지 알 수 없다.

create table if not exists public.classrooms (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null references auth.users(id) on delete cascade,
    name           text not null,
    grade          text,
    student_count  integer,
    data           jsonb not null,          -- 학급 JSON 원본 (v2.1 스키마)
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create index if not exists classrooms_user_idx
    on public.classrooms (user_id, updated_at desc);

drop trigger if exists classrooms_touch on public.classrooms;
create trigger classrooms_touch
    before update on public.classrooms
    for each row execute function public.touch_updated_at();

alter table public.classrooms enable row level security;

drop policy if exists "own classrooms" on public.classrooms;
create policy "own classrooms" on public.classrooms
    for all
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 보관 기간 정리
-- ---------------------------------------------------------------------------
--
-- 서버는 TTL(3시간)이 지난 스냅샷을 조회에서 제외할 뿐 지우지는 않는다.
-- 무료 티어 용량을 지키려면 주기적으로 이 함수를 돌린다.
--   대시보드 → Database → Cron (pg_cron)에서 매일 1회 예약 권장:
--   select cron.schedule('purge-stage-sessions', '0 18 * * *',
--                        $$select public.purge_stale_sessions(7)$$);

create or replace function public.purge_stale_sessions(keep_days integer default 7)
returns integer language plpgsql security definer as $$
declare
    removed integer;
begin
    delete from public.stage_sessions
     where saved_at < extract(epoch from now()) - (keep_days * 86400);
    get diagnostics removed = row_count;
    return removed;
end $$;
