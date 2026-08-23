"""세션 스냅샷 저장소 — 디스크와 Supabase(PostgREST)를 같은 인터페이스로 다룬다.

지금까지 스냅샷은 서버 로컬 디스크(`.sessions/`)에만 남았다. 단일 서버에서는
충분하지만, 컨테이너를 재배포하거나 서버를 여러 대로 늘리면 진행 중 수업이
사라진다. 그래서 저장 위치를 갈아끼울 수 있게 분리한다.

    SUPABASE_URL / SUPABASE_KEY 가 설정되어 있으면  → 디스크 + Supabase 이중 기록
    설정되어 있지 않으면                            → 디스크만 (기존 동작 그대로)

이중 기록(mirror)인 이유: 디스크는 빠르고 네트워크와 무관하게 확실하다.
Supabase는 서버가 바뀌어도 살아남는다. 둘 다 쓰고, 복구할 때는 더 최근 것을
고른다. 어느 쪽이 실패해도 수업은 계속된다 — 저장은 부가 기능이지 본 기능이
아니다.

인증에는 두 가지 방식이 있다 (Remote 참조).

    SUPABASE_ANON_KEY 만 있음   → RLS 모드. 요청마다 사용자 JWT로 인증하고
                                  행 접근은 데이터베이스 정책이 판단한다 (권장)
    SUPABASE_SERVICE_ROLE_KEY   → service 모드. RLS를 우회한다. 로그인 없이
                                  쓰는 운영에서는 사용자 JWT가 없어 이 방법뿐이다

환경변수:
    SUPABASE_URL       https://<project>.supabase.co
    SUPABASE_ANON_KEY  공개 키 (RLS 모드)
    SUPABASE_KEY       service_role 키 (서버 전용 — 절대 프런트엔드에 넣지 말 것)
                       SUPABASE_SERVICE_KEY / SUPABASE_SERVICE_ROLE_KEY 도 인식한다.
    SUPABASE_TABLE     스냅샷 테이블 이름 (기본 stage_sessions)

스키마는 `db/schema.sql` 참조.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("classroom_sim.web")

SAVE_TIMEOUT = 5.0    # 턴 응답을 늦추면 안 되므로 짧게
LOAD_TIMEOUT = 10.0   # 기동 시 1회뿐이라 조금 여유


class SnapshotStore:
    """스냅샷 저장소 인터페이스."""

    name = "none"

    def save(self, sid: str, payload: dict, token: str | None = None) -> None: ...

    def delete(self, sid: str, token: str | None = None) -> None: ...

    def load_all(self, newer_than: float = 0.0, limit: int = 100,
                 token: str | None = None) -> list[tuple[str, dict]]:
        """(session_id, payload) 목록을 최신순으로 돌려준다."""
        return []

    def load_one(self, sid: str, token: str | None = None) -> dict | None:
        """세션 하나만 되살린다. 지원하지 않으면 None."""
        return None


# ---------------------------------------------------------------------------
# 디스크
# ---------------------------------------------------------------------------


class DiskStore(SnapshotStore):
    """`.sessions/<sid>.json` — 원자적 교체로 쓰다 만 파일을 남기지 않는다."""

    name = "disk"

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)

    def save(self, sid: str, payload: dict, token: str | None = None) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{sid}.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dir / f"{sid}.json")

    def delete(self, sid: str, token: str | None = None) -> None:
        (self.dir / f"{sid}.json").unlink(missing_ok=True)

    def load_all(self, newer_than: float = 0.0, limit: int = 100,
                 token: str | None = None) -> list[tuple[str, dict]]:
        if not self.dir.is_dir():
            return []
        found: list[tuple[str, dict]] = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                log.warning("스냅샷을 읽지 못해 건너뜁니다: %s", f.name)
                continue
            if not isinstance(payload, dict):
                continue
            if float(payload.get("saved_at", 0) or 0) <= newer_than:
                f.unlink(missing_ok=True)   # TTL이 지난 스냅샷은 정리
                continue
            found.append((f.stem, payload))
        found.sort(key=lambda kv: float(kv[1].get("saved_at", 0) or 0), reverse=True)
        return found[:limit]

    def load_one(self, sid: str, token: str | None = None) -> dict | None:
        f = self.dir / f"{sid}.json"
        if not f.is_file():
            return None
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None


# ---------------------------------------------------------------------------
# Supabase (PostgREST)
# ---------------------------------------------------------------------------


class SupabaseStore(SnapshotStore):
    """PostgREST 위에 올린 스냅샷 저장소.

    supabase-py 의존성을 더하지 않고 httpx로 직접 호출한다. 쓰는 기능이
    upsert/delete/select 셋뿐이라 SDK를 얹을 이유가 없다.
    """

    name = "supabase"

    def __init__(self, url: str, key: str = "", table: str = "stage_sessions",
                 remote: "Remote | None" = None) -> None:
        import httpx  # fastapi가 이미 의존 — 별도 설치 불필요

        self.remote = remote or Remote(url, "", key, table)
        self.base = self.remote.url
        self.table = self.remote.table
        self.endpoint = f"{self.base}/rest/v1/{self.table}"
        self._client = httpx.Client(timeout=SAVE_TIMEOUT)

    def _h(self, token: str | None, extra: dict | None = None) -> dict:
        h = self.remote.headers(token)
        if extra:
            h.update(extra)
        return h

    def save(self, sid: str, payload: dict, token: str | None = None) -> None:
        meta = payload.get("meta") or {}
        row = {
            "id": sid,
            "user_id": meta.get("user_id") or None,   # 인증이 꺼져 있으면 null
            "saved_at": float(payload.get("saved_at") or time.time()),
            "class_name": (meta.get("class_name") or "")[:200] or None,
            "payload": payload,
        }
        r = self._client.post(
            self.endpoint,
            json=row,
            # 같은 id가 있으면 갱신 — 턴마다 새 행이 쌓이지 않게
            headers=self._h(token, {"Prefer": "resolution=merge-duplicates,return=minimal"}),
        )
        if r.status_code >= 400:
            raise RuntimeError(f"supabase upsert {r.status_code}: {r.text[:200]}")

    def delete(self, sid: str, token: str | None = None) -> None:
        r = self._client.delete(f"{self.endpoint}?id=eq.{sid}", headers=self._h(token))
        if r.status_code >= 400:
            raise RuntimeError(f"supabase delete {r.status_code}: {r.text[:200]}")

    def load_all(self, newer_than: float = 0.0, limit: int = 100,
                 token: str | None = None) -> list[tuple[str, dict]]:
        q = (
            f"{self.endpoint}?select=id,payload"
            f"&saved_at=gt.{newer_than:.0f}"
            f"&order=saved_at.desc&limit={int(limit)}"
        )
        r = self._client.get(q, timeout=LOAD_TIMEOUT, headers=self._h(token))
        if r.status_code >= 400:
            raise RuntimeError(f"supabase select {r.status_code}: {r.text[:200]}")
        rows = r.json()
        out: list[tuple[str, dict]] = []
        for row in rows if isinstance(rows, list) else []:
            sid, payload = row.get("id"), row.get("payload")
            if isinstance(sid, str) and isinstance(payload, dict):
                out.append((sid, payload))
        return out

    def load_one(self, sid: str, token: str | None = None) -> dict | None:
        """세션 하나만 되살린다 — 기동 시 전부 긁어오지 않기 위한 지연 복구용."""
        r = self._client.get(f"{self.endpoint}?select=payload&id=eq.{sid}&limit=1",
                             timeout=LOAD_TIMEOUT, headers=self._h(token))
        if r.status_code >= 400:
            raise RuntimeError(f"supabase select {r.status_code}: {r.text[:200]}")
        rows = r.json()
        if isinstance(rows, list) and rows and isinstance(rows[0].get("payload"), dict):
            return rows[0]["payload"]
        return None

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 이중 기록
# ---------------------------------------------------------------------------


class MirrorStore(SnapshotStore):
    """여러 저장소에 함께 쓰고, 읽을 때는 합쳐서 더 최근 스냅샷을 고른다.

    한쪽이 실패해도 나머지로 계속 간다. 실패는 로그로만 남기고 예외를 밖으로
    던지지 않는다 — 저장 실패로 수업이 끊기는 것이 더 나쁘다.
    """

    name = "mirror"

    def __init__(self, stores: Iterable[SnapshotStore]) -> None:
        self.stores = [s for s in stores if s is not None]
        self.name = "+".join(s.name for s in self.stores) or "none"

    def _each(self, what: str, fn) -> None:
        for s in self.stores:
            try:
                fn(s)
            except Exception as exc:
                log.warning("스냅샷 %s 실패 (%s): %s", what, s.name, exc)

    def save(self, sid: str, payload: dict, token: str | None = None) -> None:
        self._each("저장", lambda s: s.save(sid, payload, token))

    def delete(self, sid: str, token: str | None = None) -> None:
        self._each("삭제", lambda s: s.delete(sid, token))

    def load_all(self, newer_than: float = 0.0, limit: int = 100,
                 token: str | None = None) -> list[tuple[str, dict]]:
        merged: dict[str, dict] = {}
        for s in self.stores:
            try:
                rows = s.load_all(newer_than, limit, token)
            except Exception as exc:
                log.warning("스냅샷 조회 실패 (%s): %s — 나머지 저장소로 계속합니다", s.name, exc)
                continue
            for sid, payload in rows:
                cur = merged.get(sid)
                if cur is None or float(payload.get("saved_at", 0) or 0) > float(cur.get("saved_at", 0) or 0):
                    merged[sid] = payload
        out = sorted(merged.items(), key=lambda kv: float(kv[1].get("saved_at", 0) or 0), reverse=True)
        return out[:limit]

    def load_one(self, sid: str, token: str | None = None) -> dict | None:
        """저장소를 돌며 가장 최근 스냅샷을 고른다."""
        best: dict | None = None
        for s in self.stores:
            try:
                got = s.load_one(sid, token)
            except Exception as exc:
                log.warning("스냅샷 단건 조회 실패 (%s): %s", s.name, exc)
                continue
            if got and (best is None or
                        float(got.get("saved_at", 0) or 0) > float(best.get("saved_at", 0) or 0)):
                best = got
        return best


# ---------------------------------------------------------------------------
# 구성
# ---------------------------------------------------------------------------


class Remote:
    """Supabase 접속 방식. 어떤 키로 어떻게 인증할지를 한곳에서 정한다.

    두 가지 모드가 있다.

    **RLS 모드** (권장) — anon 키만 서버에 둔다. 요청마다 그 사용자의 JWT를
    Authorization에 실어 보내고, 행 접근은 데이터베이스의 RLS 정책이 판단한다.
    서버가 털려도 남의 데이터를 꺼낼 수 있는 키가 없다.

    **service 모드** — service_role 키로 RLS를 우회한다. 로그인이 없는 운영
    (같은 Wi-Fi 안에서 혼자 쓰기)에서는 사용자 JWT가 없으므로 이 방법뿐이다.

    두 키가 다 있으면 RLS 모드를 쓴다 — 더 안전한 쪽이 기본이어야 한다.
    """

    def __init__(self, url: str, anon_key: str, service_key: str, table: str) -> None:
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.service_key = service_key
        self.table = table

    @property
    def rls_mode(self) -> bool:
        return bool(self.anon_key)

    @property
    def apikey(self) -> str:
        return self.anon_key or self.service_key

    def headers(self, token: str | None = None) -> dict:
        """요청 헤더. RLS 모드에서는 사용자 JWT로, 아니면 service 키로 인증한다."""
        bearer = token if (self.rls_mode and token) else (self.service_key or self.anon_key)
        return {"apikey": self.apikey, "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json"}

    @property
    def needs_token(self) -> bool:
        """RLS 모드이면서 service 키가 없으면, 토큰 없는 요청은 아무것도 못 한다."""
        return self.rls_mode and not self.service_key

    def describe(self) -> str:
        return "RLS(사용자 토큰)" if self.needs_token else "service_role"


def remote_config(table: str = "stage_sessions") -> Remote | None:
    """환경변수에서 Supabase 접속 설정을 읽는다. 쓸 수 없으면 None."""
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    anon = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    service = (
        os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not url or not (anon or service):
        return None
    if not url.startswith(("http://", "https://")):
        log.warning("SUPABASE_URL이 http(s)로 시작하지 않아 무시합니다: %r", url[:40])
        return None
    tbl = (os.environ.get("SUPABASE_TABLE") or table).strip() or table
    return Remote(url, anon, service, tbl)


def supabase_config() -> tuple[str, str, str] | None:
    """(url, key, table). Remote를 쓰지 않는 호출부를 위한 얇은 호환 함수."""
    r = remote_config()
    if r is None:
        return None
    return r.url, (r.service_key or r.anon_key), r.table


def stateless() -> bool:
    """서버리스(Vercel 등)에서 도는가?

    서버리스는 요청마다 다른 인스턴스일 수 있고 로컬 디스크가 남지 않는다.
    그래서 디스크 저장소를 아예 붙이지 않고 원격만 쓴다. 붙여 두면 "저장됐다"고
    믿었다가 다음 요청에서 사라지는, 가장 나쁜 종류의 실패가 난다.

    Vercel은 VERCEL 환경변수를 자동으로 넣어 준다. 다른 서버리스 환경에서는
    CLASSROOM_SIM_STATELESS=1 로 직접 켠다.
    """
    if (os.environ.get("CLASSROOM_SIM_STATELESS") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def make_store(disk_dir: Path) -> SnapshotStore:
    """환경변수를 보고 저장소를 구성한다."""
    remote = remote_config()
    remote_store: SnapshotStore | None = None
    if remote:
        try:
            remote_store = SupabaseStore("", remote=remote)
        except Exception as exc:
            log.warning("Supabase 저장소를 만들지 못했습니다: %s", exc)

    if stateless():
        # 디스크는 쓰지 않는다 — 다음 요청이 다른 인스턴스일 수 있다
        if remote_store is None:
            log.error("서버리스인데 Supabase가 설정되지 않았습니다 — 수업이 턴마다 사라집니다. "
                      "SUPABASE_URL 과 키를 설정하세요.")
            return SnapshotStore()          # 아무 데도 저장하지 않음 (명시적)
        log.info("세션 스냅샷: Supabase 전용 (서버리스 — %s, 인증 %s)",
                 remote.url, remote.describe())
        return remote_store

    stores: list[SnapshotStore] = [DiskStore(disk_dir)]
    if remote_store is not None:
        stores.append(remote_store)
        log.info("세션 스냅샷: 디스크 + Supabase(%s, 테이블 %s, 인증 %s)",
                 remote.url, remote.table, remote.describe())
    if len(stores) == 1:
        return stores[0]
    return MirrorStore(stores)
