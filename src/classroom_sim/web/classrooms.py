"""내 학급 저장소 — 교사가 만든 학급을 사용자별로 보관한다.

지금까지 학급은 저장소의 `personas/*.json` 파일뿐이었다. 서버 파일을 직접
고칠 수 있는 사람만 자기 학급을 만들 수 있다는 뜻이라, 로그인이 붙은 지금은
말이 되지 않는다. 그래서 두 갈래로 나눈다.

    샘플 학급  personas/*.json      모두에게 읽기 전용으로 보인다
    내 학급    Supabase 또는 디스크  만든 사람에게만 보이고, 지우기도 가능

저장 위치는 설정을 따른다.

    SUPABASE_URL/KEY 있음  → classrooms 테이블 (서버가 바뀌어도 남는다)
    없음                   → `.classrooms/` 디렉터리 (로그인 없이 혼자 쓸 때)

세션 스냅샷(store.py)과 달리 이중 기록을 하지 않는다. 스냅샷은 몇 시간이면
사라지는 사본이라 어느 쪽이 남아도 그만이지만, 학급은 교사가 직접 만든
원본이다. 두 곳에 두면 서로 어긋났을 때 무엇이 맞는지 알 수 없다.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path

from ..personas import Classroom, load_classroom, parse_classroom
from .store import SAVE_TIMEOUT, Remote, remote_config, stateless

log = logging.getLogger("classroom_sim.web")

MAX_PER_USER = 50          # 한 사람이 만들 수 있는 학급 수
MAX_JSON_BYTES = 512 * 1024


class ClassroomError(Exception):
    """호출부가 400으로 바꾼다."""


def _summary(cid: str, c: Classroom, data: dict, mine: bool) -> dict:
    """목록 화면에 필요한 만큼만 추린다 (학생 전체를 실어 보내지 않는다)."""
    return {
        "id": cid,
        "class_name": c.class_name,
        "grade": c.grade,
        "count": len(c.students),
        "mine": mine,
    }


# ---------------------------------------------------------------------------
# 샘플 (저장소 파일 — 읽기 전용)
# ---------------------------------------------------------------------------


class SampleClassrooms:
    """`personas/*.json`. 누구에게나 보이고 아무도 지울 수 없다."""

    def __init__(self, root: Path) -> None:
        self.dir = Path(root) / "personas"

    def list(self) -> list[dict]:
        out: list[dict] = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                c = load_classroom(p)
            except Exception:
                continue        # 망가진 샘플은 목록에서 조용히 뺀다
            out.append({
                "id": f"sample:{p.stem}",
                "class_name": c.class_name,
                "grade": c.grade,
                "count": len(c.students),
                "mine": False,
                "path": str(p.relative_to(self.dir.parent)),
            })
        return out

    def get(self, cid: str) -> tuple[Classroom, dict] | None:
        stem = cid.split(":", 1)[1] if ":" in cid else cid
        if not re.fullmatch(r"[\w가-힣 .-]{1,80}", stem):
            return None                                  # 경로 탈출 차단
        p = (self.dir / f"{stem}.json").resolve()
        if not p.is_file() or self.dir.resolve() not in p.parents:
            return None
        # 파일이 깨졌을 때는 None(=없음)이 아니라 검증 오류를 그대로 올려 보낸다.
        # "찾을 수 없습니다"보다 "학생 x에 id가 없습니다"가 고칠 수 있는 안내다.
        return load_classroom(p), json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 내 학급
# ---------------------------------------------------------------------------


class MyClassrooms:
    """사용자별 학급 저장소 인터페이스."""

    name = "none"

    def list(self, user_id: str, token: str | None = None) -> list[dict]:
        return []

    def get(self, user_id: str, cid: str, token: str | None = None) -> dict | None:
        return None

    def create(self, user_id: str, data: dict, cid: str, token: str | None = None) -> None:
        raise ClassroomError("학급 저장소가 설정되지 않았습니다. 관리자에게 문의해 주세요.")

    def delete(self, user_id: str, cid: str, token: str | None = None) -> bool:
        return False


class DiskClassrooms(MyClassrooms):
    """`.classrooms/<user>/<id>.json`. 로그인 없이 혼자 쓸 때의 기본값."""

    name = "disk"

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)

    def _user_dir(self, user_id: str) -> Path:
        # 사용자 id가 경로가 되지 않게 안전한 문자만 남긴다
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id or "local")[:64] or "local"
        return self.dir / safe

    def list(self, user_id: str, token: str | None = None) -> list[dict]:
        d = self._user_dir(user_id)
        if not d.is_dir():
            return []
        rows: list[tuple[float, dict]] = []
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                c = parse_classroom(data, f.stem)
            except Exception:
                continue
            rows.append((f.stat().st_mtime, _summary(f.stem, c, data, True)))
        rows.sort(key=lambda r: r[0], reverse=True)
        return [r[1] for r in rows]

    def get(self, user_id: str, cid: str, token: str | None = None) -> dict | None:
        f = self._user_dir(user_id) / f"{cid}.json"
        if not f.is_file():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None

    def create(self, user_id: str, data: dict, cid: str, token: str | None = None) -> None:
        d = self._user_dir(user_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{cid}.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / f"{cid}.json")

    def delete(self, user_id: str, cid: str, token: str | None = None) -> bool:
        f = self._user_dir(user_id) / f"{cid}.json"
        if not f.is_file():
            return False
        f.unlink()
        return True


class SupabaseClassrooms(MyClassrooms):
    """`classrooms` 테이블 (PostgREST)."""

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
            raise ClassroomError(f"학급 {what}에 실패했습니다 ({r.status_code}).")
        return r

    def _call(self, what: str, fn):
        """연결 자체가 안 될 때도 원시 예외 대신 알아들을 수 있는 말로 바꾼다."""
        import httpx

        try:
            return self._check(fn(), what)
        except httpx.HTTPError as exc:
            log.warning("%s %s 실패(연결): %s", "학급", what, exc)
            raise ClassroomError(f"저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc

    def list(self, user_id: str, token: str | None = None) -> list[dict]:
        r = self._call("목록 조회", lambda: self._client.get(
            f"{self.endpoint}?select=id,data&user_id=eq.{user_id}"
            f"&order=updated_at.desc&limit={MAX_PER_USER}", headers=self._h(token)))
        out: list[dict] = []
        for row in r.json() or []:
            try:
                c = parse_classroom(row["data"], str(row["id"]))
            except Exception:
                continue
            out.append(_summary(str(row["id"]), c, row["data"], True))
        return out

    def get(self, user_id: str, cid: str, token: str | None = None) -> dict | None:
        r = self._call("조회", lambda: self._client.get(
            f"{self.endpoint}?select=data&id=eq.{cid}&user_id=eq.{user_id}&limit=1",
            headers=self._h(token)))
        rows = r.json() or []
        return rows[0]["data"] if rows else None

    def create(self, user_id: str, data: dict, cid: str, token: str | None = None) -> None:
        c = parse_classroom(data)
        self._call("저장", lambda: self._client.post(self.endpoint, json={
            "id": cid, "user_id": user_id,
            "name": c.class_name[:200], "grade": (c.grade or "")[:50],
            "student_count": len(c.students), "data": data,
        }, headers=self._h(token, {"Prefer": "return=minimal"})))

    def delete(self, user_id: str, cid: str, token: str | None = None) -> bool:
        r = self._call("삭제", lambda: self._client.delete(
            f"{self.endpoint}?id=eq.{cid}&user_id=eq.{user_id}",
            headers=self._h(token, {"Prefer": "return=representation"})))
        try:
            return bool(r.json())
        except Exception:
            return True


# ---------------------------------------------------------------------------
# 묶음
# ---------------------------------------------------------------------------


class ClassroomLibrary:
    """샘플 + 내 학급을 한 화면에 보여 주기 위한 묶음."""

    def __init__(self, root: Path, disk_dir: Path) -> None:
        self.samples = SampleClassrooms(root)
        cfg = remote_config("classrooms")
        self.mine: MyClassrooms = MyClassrooms()
        if cfg:
            try:
                self.mine = SupabaseClassrooms(cfg)
                log.info("내 학급 저장소: Supabase (classrooms 테이블, 인증 %s)", cfg.describe())
                return
            except Exception as exc:
                log.warning("Supabase 학급 저장소를 만들지 못했습니다: %s", exc)
        if stateless():
            # 서버리스에서 디스크로 폴백하면 다음 요청에서 학급이 사라진다.
            # 저장이 안 되는 것보다, 안 된다고 말하는 편이 낫다.
            log.error("서버리스인데 Supabase가 없습니다 — 내 학급을 만들 수 없습니다.")
        else:
            self.mine = DiskClassrooms(disk_dir)

    @property
    def name(self) -> str:
        return self.mine.name

    def list(self, user_id: str | None, token: str | None = None) -> list[dict]:
        out = self.samples.list()
        try:
            out = self.mine.list(user_id or "local", token) + out   # 내 학급을 위에
        except Exception as exc:
            # 내 학급을 못 읽어도 샘플로 수업은 시작할 수 있어야 한다
            log.warning("내 학급 목록 조회 실패: %s", exc)
        return out

    def resolve(self, user_id: str | None, cid: str, token: str | None = None) -> tuple[Classroom, dict]:
        """학급 id로 Classroom을 얻는다. 없으면 ClassroomError."""
        if cid.startswith("sample:"):
            got = self.samples.get(cid)
            if got is None:
                raise ClassroomError("샘플 학급을 찾을 수 없습니다.")
            return got
        data = self.mine.get(user_id or "local", cid, token)
        if data is None:
            raise ClassroomError("학급을 찾을 수 없습니다. 목록을 새로고침해 주세요.")
        return parse_classroom(data, "학급"), data

    def create(self, user_id: str | None, text: str, token: str | None = None) -> dict:
        """교사가 붙여넣거나 올린 학급 JSON을 검증해 저장한다."""
        from ..personas import loads_classroom

        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            raise ClassroomError("학급 파일이 너무 큽니다 (512KB 초과).")
        c = loads_classroom(text, "학급 파일")       # 형식 오류를 한국어로 짚어 준다
        if len(c.students) > 40:
            raise ClassroomError(f"학급 인원이 너무 많습니다 ({len(c.students)}명). 최대 40명까지 지원합니다.")
        uid = user_id or "local"
        existing = self.mine.list(uid, token)
        if len(existing) >= MAX_PER_USER:
            raise ClassroomError(f"학급을 {MAX_PER_USER}개까지만 만들 수 있습니다. 쓰지 않는 학급을 지워 주세요.")
        data = json.loads(text)
        cid = str(uuid.uuid4())
        self.mine.create(uid, data, cid, token)
        log.info("classroom created: %s user=%s name=%s students=%d",
                 cid[:8], (uid or "-")[:8], c.class_name, len(c.students))
        return _summary(cid, c, data, True)

    def delete(self, user_id: str | None, cid: str, token: str | None = None) -> None:
        if cid.startswith("sample:"):
            raise ClassroomError("샘플 학급은 지울 수 없습니다.")
        if not self.mine.delete(user_id or "local", cid, token):
            raise ClassroomError("학급을 찾을 수 없습니다.")
        log.info("classroom deleted: %s user=%s", cid[:8], (user_id or "-")[:8])
