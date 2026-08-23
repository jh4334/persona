"""수업 기록 저장소 — 끝난 수업의 리포트와 전사를 보관한다.

지금까지 리포트는 서버 디스크(`reports/stage/`)에만 남았다. 두 가지가 아쉬웠다.

    · 컨테이너를 재배포하면 사라진다
    · 교사가 리포트 화면을 벗어나면 다시 찾을 방법이 없다 (파일을 직접 뒤지지 않는 한)

그래서 목록·열람이 가능한 저장소로 만든다. 디스크 파일 쓰기는 그대로 둔다 —
서버에 남는 파일은 그 자체로 쓸모가 있고, 이미 그렇게 동작하고 있었다.
목록과 열람은 Supabase가 설정돼 있으면 거기서, 아니면 디스크에서 읽는다.

디스크 저장 형식 (기존 파일 옆에 meta 하나가 늘었다):

    reports/stage/20260818_150337_6학년3반_a1b2c3d4.md
    reports/stage/20260818_150337_6학년3반_a1b2c3d4.transcript.json
    reports/stage/20260818_150337_6학년3반_a1b2c3d4.meta.json   ← 목록에 필요한 것만
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from .store import SAVE_TIMEOUT, Remote, remote_config, stateless

log = logging.getLogger("classroom_sim.web")

MAX_LIST = 100
MAX_MD_BYTES = 2 * 1024 * 1024      # 리포트 본문 상한 (원격 저장 시)


class ReportError(Exception):
    """호출부가 404/400으로 바꾼다."""


def _row(meta: dict) -> dict:
    """목록에 내보낼 요약 — 본문·전사는 빼고 가볍게."""
    return {
        "id": meta.get("id", ""),
        "class_name": meta.get("class_name", ""),
        "lesson_title": meta.get("lesson_title", ""),
        "created_at": float(meta.get("created_at") or 0),
        "turns": int(meta.get("turns") or 0),
        "minutes": int(meta.get("minutes") or 0),
    }


# ---------------------------------------------------------------------------
# 디스크
# ---------------------------------------------------------------------------


class DiskReports:
    name = "disk"

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)

    def save(self, meta: dict, markdown: str, transcript: object, base: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{base}.md").write_text(markdown or "", encoding="utf-8")
        if transcript is not None:
            (self.dir / f"{base}.transcript.json").write_text(
                json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.dir / f"{base}.meta.json").write_text(
            json.dumps({**meta, "base": base}, ensure_ascii=False), encoding="utf-8")

    def _metas(self, user_id: str) -> list[dict]:
        if not self.dir.is_dir():
            return []
        out = []
        for f in self.dir.glob("*.meta.json"):
            try:
                m = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (m.get("user_id") or "") == (user_id or ""):
                out.append(m)
        out.sort(key=lambda m: float(m.get("created_at") or 0), reverse=True)
        return out

    def list(self, user_id: str) -> list[dict]:
        return [_row(m) for m in self._metas(user_id)[:MAX_LIST]]

    def _find(self, user_id: str, rid: str) -> dict | None:
        for m in self._metas(user_id):
            if m.get("id") == rid:
                return m
        return None

    def get(self, user_id: str, rid: str) -> dict | None:
        m = self._find(user_id, rid)
        if not m:
            return None
        base = m.get("base") or ""
        md = self.dir / f"{base}.md"
        tj = self.dir / f"{base}.transcript.json"
        out = dict(_row(m))
        out["markdown"] = md.read_text(encoding="utf-8") if md.is_file() else ""
        try:
            out["transcript"] = json.loads(tj.read_text(encoding="utf-8")) if tj.is_file() else []
        except Exception:
            out["transcript"] = []
        return out

    def delete(self, user_id: str, rid: str) -> bool:
        m = self._find(user_id, rid)
        if not m:
            return False
        base = m.get("base") or ""
        for suffix in (".md", ".transcript.json", ".meta.json"):
            (self.dir / f"{base}{suffix}").unlink(missing_ok=True)
        return True


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------


class SupabaseReports:
    name = "supabase"

    def __init__(self, remote: Remote) -> None:
        import httpx

        self.remote = remote
        self.endpoint = f"{remote.url}/rest/v1/{remote.table}"
        self._client = httpx.Client(timeout=SAVE_TIMEOUT)

    def _h(self, token, extra=None):
        h = self.remote.headers(token)
        if extra:
            h.update(extra)
        return h

    def _check(self, r, what: str):
        if r.status_code >= 400:
            raise ReportError(f"수업 기록 {what}에 실패했습니다 ({r.status_code}).")
        return r

    def _call(self, what: str, fn):
        """연결 자체가 안 될 때도 원시 예외 대신 알아들을 수 있는 말로 바꾼다."""
        import httpx

        try:
            return self._check(fn(), what)
        except httpx.HTTPError as exc:
            log.warning("%s %s 실패(연결): %s", "수업 기록", what, exc)
            raise ReportError(f"저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc

    def save(self, meta: dict, markdown: str, transcript: object,
             token: str | None = None) -> None:
        self._call("저장", lambda: self._client.post(self.endpoint, json={
            "id": meta["id"],
            "user_id": meta.get("user_id") or None,
            "session_id": meta.get("session_id", ""),
            "class_name": meta.get("class_name", "")[:200],
            "lesson_title": meta.get("lesson_title", "")[:200],
            "turns": int(meta.get("turns") or 0),
            "minutes": int(meta.get("minutes") or 0),
            "markdown": (markdown or "")[:MAX_MD_BYTES],
            "transcript": transcript if transcript is not None else [],
            "created_at_epoch": float(meta.get("created_at") or time.time()),
        }, headers=self._h(token, {"Prefer": "return=minimal"})))

    def list(self, user_id: str, token: str | None = None) -> list[dict]:
        r = self._call("목록 조회", lambda: self._client.get(
            f"{self.endpoint}?select=id,class_name,lesson_title,turns,minutes,created_at_epoch"
            f"&user_id=eq.{user_id}&order=created_at_epoch.desc&limit={MAX_LIST}",
            headers=self._h(token)))
        return [_row({**row, "created_at": row.get("created_at_epoch")}) for row in r.json() or []]

    def get(self, user_id: str, rid: str, token: str | None = None) -> dict | None:
        r = self._call("조회", lambda: self._client.get(
            f"{self.endpoint}?select=*&id=eq.{rid}&user_id=eq.{user_id}&limit=1",
            headers=self._h(token)))
        rows = r.json() or []
        if not rows:
            return None
        row = rows[0]
        out = _row({**row, "created_at": row.get("created_at_epoch")})
        out["markdown"] = row.get("markdown") or ""
        out["transcript"] = row.get("transcript") or []
        return out

    def delete(self, user_id: str, rid: str, token: str | None = None) -> bool:
        r = self._call("삭제", lambda: self._client.delete(
            f"{self.endpoint}?id=eq.{rid}&user_id=eq.{user_id}",
            headers=self._h(token, {"Prefer": "return=representation"})))
        try:
            return bool(r.json())
        except Exception:
            return True


# ---------------------------------------------------------------------------
# 묶음
# ---------------------------------------------------------------------------


class ReportLibrary:
    """디스크 파일은 늘 남기고, 목록·열람은 설정된 저장소에서 한다."""

    def __init__(self, disk_dir: Path) -> None:
        # 서버리스에서는 디스크에 써도 다음 요청에서 사라진다 — 아예 쓰지 않는다
        self.use_disk = not stateless()
        self.disk = DiskReports(disk_dir)
        cfg = remote_config("reports")
        self.remote: SupabaseReports | None = None
        if cfg:
            try:
                self.remote = SupabaseReports(cfg)
                log.info("수업 기록 저장소: Supabase (reports 테이블, 인증 %s)", cfg.describe())
            except Exception as exc:
                log.warning("Supabase 기록 저장소를 만들지 못했습니다 (디스크 사용): %s", exc)

    @property
    def name(self) -> str:
        if self.remote:
            return "disk+supabase" if self.use_disk else "supabase"
        return "disk" if self.use_disk else "none"

    def save(self, meta: dict, markdown: str, transcript: object, base: str,
             token: str | None = None) -> str:
        """리포트를 남기고 기록 id를 돌려준다. 원격이 실패해도 디스크는 남는다."""
        meta = {**meta, "id": meta.get("id") or str(uuid.uuid4()),
                "created_at": meta.get("created_at") or time.time()}
        if self.use_disk:
            self.disk.save(meta, markdown, transcript, base)
        if self.remote:
            try:
                self.remote.save(meta, markdown, transcript, token)
            except Exception as exc:
                log.warning("수업 기록 원격 저장 실패 (디스크에는 남았습니다): %s", exc)
        return meta["id"]

    def list(self, user_id: str | None, token: str | None = None) -> list[dict]:
        uid = user_id or ""
        if self.remote:
            try:
                return self.remote.list(uid or "local", token)
            except Exception as exc:
                log.warning("수업 기록 원격 조회 실패 (디스크로 대체): %s", exc)
        return self.disk.list(uid) if self.use_disk else []

    def get(self, user_id: str | None, rid: str, token: str | None = None) -> dict:
        uid = user_id or ""
        got = None
        if self.remote:
            try:
                got = self.remote.get(uid or "local", rid, token)
            except Exception as exc:
                log.warning("수업 기록 원격 열람 실패 (디스크로 대체): %s", exc)
        if got is None and self.use_disk:
            got = self.disk.get(uid, rid)
        if got is None:
            raise ReportError("수업 기록을 찾을 수 없습니다.")
        return got

    def delete(self, user_id: str | None, rid: str, token: str | None = None) -> None:
        uid = user_id or ""
        hit = self.disk.delete(uid, rid) if self.use_disk else False
        if self.remote:
            try:
                hit = self.remote.delete(uid or "local", rid, token) or hit
            except Exception as exc:
                log.warning("수업 기록 원격 삭제 실패: %s", exc)
        if not hit:
            raise ReportError("수업 기록을 찾을 수 없습니다.")
