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

환경변수:
    SUPABASE_URL   https://<project>.supabase.co
    SUPABASE_KEY   service_role 키 (서버 전용 — 절대 프런트엔드에 넣지 말 것)
                   SUPABASE_SERVICE_KEY / SUPABASE_SERVICE_ROLE_KEY 도 인식한다.
    SUPABASE_TABLE 스냅샷 테이블 이름 (기본 stage_sessions)

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

    def save(self, sid: str, payload: dict) -> None: ...

    def delete(self, sid: str) -> None: ...

    def load_all(self, newer_than: float = 0.0, limit: int = 100) -> list[tuple[str, dict]]:
        """(session_id, payload) 목록을 최신순으로 돌려준다."""
        return []


# ---------------------------------------------------------------------------
# 디스크
# ---------------------------------------------------------------------------


class DiskStore(SnapshotStore):
    """`.sessions/<sid>.json` — 원자적 교체로 쓰다 만 파일을 남기지 않는다."""

    name = "disk"

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)

    def save(self, sid: str, payload: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{sid}.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dir / f"{sid}.json")

    def delete(self, sid: str) -> None:
        (self.dir / f"{sid}.json").unlink(missing_ok=True)

    def load_all(self, newer_than: float = 0.0, limit: int = 100) -> list[tuple[str, dict]]:
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


# ---------------------------------------------------------------------------
# Supabase (PostgREST)
# ---------------------------------------------------------------------------


class SupabaseStore(SnapshotStore):
    """PostgREST 위에 올린 스냅샷 저장소.

    supabase-py 의존성을 더하지 않고 httpx로 직접 호출한다. 쓰는 기능이
    upsert/delete/select 셋뿐이라 SDK를 얹을 이유가 없다.
    """

    name = "supabase"

    def __init__(self, url: str, key: str, table: str = "stage_sessions") -> None:
        import httpx  # fastapi가 이미 의존 — 별도 설치 불필요

        self.base = url.rstrip("/")
        self.table = table
        self.endpoint = f"{self.base}/rest/v1/{table}"
        self._client = httpx.Client(
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=SAVE_TIMEOUT,
        )

    def save(self, sid: str, payload: dict) -> None:
        meta = payload.get("meta") or {}
        row = {
            "id": sid,
            "saved_at": float(payload.get("saved_at") or time.time()),
            "class_name": (meta.get("class_name") or "")[:200] or None,
            "payload": payload,
        }
        r = self._client.post(
            self.endpoint,
            json=row,
            # 같은 id가 있으면 갱신 — 턴마다 새 행이 쌓이지 않게
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"supabase upsert {r.status_code}: {r.text[:200]}")

    def delete(self, sid: str) -> None:
        r = self._client.delete(f"{self.endpoint}?id=eq.{sid}")
        if r.status_code >= 400:
            raise RuntimeError(f"supabase delete {r.status_code}: {r.text[:200]}")

    def load_all(self, newer_than: float = 0.0, limit: int = 100) -> list[tuple[str, dict]]:
        q = (
            f"{self.endpoint}?select=id,payload"
            f"&saved_at=gt.{newer_than:.0f}"
            f"&order=saved_at.desc&limit={int(limit)}"
        )
        r = self._client.get(q, timeout=LOAD_TIMEOUT)
        if r.status_code >= 400:
            raise RuntimeError(f"supabase select {r.status_code}: {r.text[:200]}")
        rows = r.json()
        out: list[tuple[str, dict]] = []
        for row in rows if isinstance(rows, list) else []:
            sid, payload = row.get("id"), row.get("payload")
            if isinstance(sid, str) and isinstance(payload, dict):
                out.append((sid, payload))
        return out

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

    def save(self, sid: str, payload: dict) -> None:
        self._each("저장", lambda s: s.save(sid, payload))

    def delete(self, sid: str) -> None:
        self._each("삭제", lambda s: s.delete(sid))

    def load_all(self, newer_than: float = 0.0, limit: int = 100) -> list[tuple[str, dict]]:
        merged: dict[str, dict] = {}
        for s in self.stores:
            try:
                rows = s.load_all(newer_than, limit)
            except Exception as exc:
                log.warning("스냅샷 조회 실패 (%s): %s — 나머지 저장소로 계속합니다", s.name, exc)
                continue
            for sid, payload in rows:
                cur = merged.get(sid)
                if cur is None or float(payload.get("saved_at", 0) or 0) > float(cur.get("saved_at", 0) or 0):
                    merged[sid] = payload
        out = sorted(merged.items(), key=lambda kv: float(kv[1].get("saved_at", 0) or 0), reverse=True)
        return out[:limit]


# ---------------------------------------------------------------------------
# 구성
# ---------------------------------------------------------------------------


def supabase_config() -> tuple[str, str, str] | None:
    """환경변수에서 (url, key, table)을 읽는다. 하나라도 없으면 None."""
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not url or not key:
        return None
    if not url.startswith(("http://", "https://")):
        log.warning("SUPABASE_URL이 http(s)로 시작하지 않아 무시합니다: %r", url[:40])
        return None
    table = (os.environ.get("SUPABASE_TABLE") or "stage_sessions").strip() or "stage_sessions"
    return url, key, table


def make_store(disk_dir: Path) -> SnapshotStore:
    """환경변수를 보고 저장소를 구성한다. 디스크는 항상 포함된다."""
    stores: list[SnapshotStore] = [DiskStore(disk_dir)]
    cfg = supabase_config()
    if cfg:
        url, key, table = cfg
        try:
            stores.append(SupabaseStore(url, key, table))
            log.info("세션 스냅샷: 디스크 + Supabase(%s, 테이블 %s)", url, table)
        except Exception as exc:
            log.warning("Supabase 저장소를 만들지 못했습니다 (디스크만 사용): %s", exc)
    if len(stores) == 1:
        return stores[0]
    return MirrorStore(stores)
