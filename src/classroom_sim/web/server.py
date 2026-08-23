"""보이는 교실 — FastAPI 웹 서버.

`docs/specs/stage_contract.md`의 웹 API 표를 그대로 구현한다.
세션은 프로토타입답게 메모리 dict에 보관하고, 응답 직렬화는
dataclasses.asdict 기반이다.

실행:
    PYTHONPATH=src uvicorn classroom_sim.web.server:app --port 8000
    PYTHONPATH=src python -m classroom_sim.web --port 8000

환경변수:
    CLASSROOM_SIM_FAKE=1   엔진(stage/) 대신 web/dev_fake.py의 FakeSession 사용
                           (엔진이 아직 없어도 프론트엔드를 완전히 개발·테스트 가능)
    CLASSROOM_SIM_ROOT     personas/·lessons/ 를 찾을 저장소 루트 (기본: 자동 탐지)
    SUPABASE_URL/_KEY      설정하면 세션 스냅샷을 디스크와 Supabase에 함께 기록
                           (미설정이면 디스크만 — 자세한 내용은 web/store.py)
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..personas import Classroom, load_classroom, parse_classroom
from . import auth as _auth
from ..stage import incidents as _incidents
from . import mcp as _mcp
from .classrooms import ClassroomError, ClassroomLibrary
from .reports import ReportError, ReportLibrary
from .store import DiskStore, make_store, remote_config, stateless

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"


def _repo_root() -> Path:
    """personas/ 와 lessons/ 가 있는 저장소 루트를 찾는다."""
    env = os.environ.get("CLASSROOM_SIM_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # src/classroom_sim/web/server.py → src/classroom_sim/web → ... → 저장소 루트
    for parent in Path(__file__).resolve().parents:
        if (parent / "personas").is_dir() and (parent / "lessons").is_dir():
            return parent
    return Path.cwd()


ROOT = _repo_root()
START_TIME = time.time()

# 운영 진단용 로거 — "느려요/안 돼요"가 왔을 때 서버 터미널만 보고 원인을 좁힐 수 있게 한다.
log = logging.getLogger("classroom_sim.web")


def _use_fake() -> bool:
    return os.environ.get("CLASSROOM_SIM_FAKE", "").strip() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# 지연 임포트 — 엔진은 다른 에이전트가 동시에 구현 중이므로 요청 시점에 불러온다.
# ---------------------------------------------------------------------------


def _make_session(classroom: Classroom, lesson_text: str, backend_name: str, seed: int | None):
    """StageSession(또는 개발용 FakeSession) 인스턴스를 만든다."""
    if _use_fake():
        from .dev_fake import FakeSession

        return FakeSession(classroom, lesson_text, backend=None, seed=seed), "fake"

    try:
        from ..stage.backend import make_backend  # type: ignore
        from ..stage.session import StageSession  # type: ignore
    except Exception as exc:  # 엔진 미완성/부재
        raise HTTPException(
            status_code=503,
            detail=(
                "무대 엔진(classroom_sim.stage)을 불러올 수 없습니다: "
                f"{exc}. 개발 중에는 CLASSROOM_SIM_FAKE=1 로 실행하세요."
            ),
        ) from exc

    try:
        backend = make_backend(backend_name)
        return StageSession(classroom, lesson_text, backend=backend, seed=seed), backend_name
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"세션 생성 실패: {exc}") from exc


# ---------------------------------------------------------------------------
# 세션 저장소 (메모리)
# ---------------------------------------------------------------------------


MAX_SESSIONS = 30          # 동시 보관 세션 상한 (프로토타입 서버 보호)
SESSION_IDLE_TTL = 3 * 3600  # 마지막 사용 후 3시간 지나면 회수


class SessionRecord:
    def __init__(self, session: Any, classroom: Classroom, meta: dict) -> None:
        self.session = session
        self.classroom = classroom
        self.meta = meta
        self.lock = threading.Lock()      # 턴 처리 직렬화 (동시 요청 경쟁 방지)
        self.last_used = time.time()

    # RLS 모드에서는 이 토큰으로 Supabase에 쓴다. 요청마다 최신 것으로 갱신한다.
    token: str | None = None

    @property
    def user_id(self) -> str | None:
        """이 수업의 주인. 인증을 끄고 쓰면 None."""
        return self.meta.get("user_id")

    def touch(self) -> None:
        self.last_used = time.time()


SESSIONS: dict[str, SessionRecord] = {}
_SESSIONS_GUARD = threading.Lock()

# 세션 스냅샷 — 서버가 재시작돼도 진행 중 수업을 되살릴 수 있게 남긴다.
# 저장 위치는 store.make_store가 정한다: 디스크 기본, SUPABASE_* 설정 시 이중 기록.
SNAP_DIR = ROOT / ".sessions"
STORE = make_store(SNAP_DIR)
DISK_STORE = DiskStore(SNAP_DIR)     # 기동 복구는 디스크만 본다 (아래 _restore_sessions 참조)

# 학급 서가 — 저장소의 샘플(읽기 전용) + 교사가 만든 내 학급(사용자별)
LIBRARY = ClassroomLibrary(ROOT, ROOT / ".classrooms")

# 수업 기록 — 끝난 수업의 리포트·전사 (디스크에 늘 남기고, 설정 시 Supabase에도)
REPORTS = ReportLibrary(ROOT / "reports" / "stage")


def _persist_session(sid: str, rec: SessionRecord) -> bool:
    """턴이 끝날 때마다 세션 상태를 저장한다. 저장에 성공했으면 True.

    일반 서버에서는 실패해도 수업이 계속된다 — 메모리에 세션이 남아 있고
    디스크에도 사본이 있다. 서버리스는 다르다. 저장이 실패하면 다음 요청이
    다른 인스턴스에 닿는 순간 수업이 통째로 사라지므로, 교사에게 알려야 한다.
    """
    if not hasattr(rec.session, "dump_state"):
        return True  # FakeSession 등 스냅샷 미지원 세션
    try:
        STORE.save(sid, {
            "meta": rec.meta,
            "saved_at": time.time(),
            "snapshot": rec.session.dump_state(),
        }, token=rec.token)
        return True
    except Exception:
        log.exception("session persist failed: %s", sid[:8])
        return False


def _drop_snapshot(sid: str, token: str | None = None) -> None:
    try:
        STORE.delete(sid, token=token)
    except Exception:
        pass


def _rebuild(sid: str, payload: dict, token: str | None = None) -> SessionRecord | None:
    """스냅샷 하나를 살아 있는 세션으로 되돌린다. 되살릴 수 없으면 None."""
    saved_at = float(payload.get("saved_at", 0))
    snap = payload.get("snapshot") or {}
    if snap.get("state", {}).get("ended"):
        return None
    if time.time() - saved_at > SESSION_IDLE_TTL:
        return None
    meta = payload.get("meta") or {}
    classroom = _classroom_of(meta, token)
    lesson_text = (ROOT / meta["lesson_path"]).read_text(encoding="utf-8")
    session, _ = _make_session(classroom, lesson_text, meta.get("backend", "mock"), None)
    session.load_state(snap)
    rec = SessionRecord(session, classroom, dict(meta))
    rec.last_used = saved_at
    rec.token = token
    return rec


def _restore_sessions() -> None:
    """서버 기동 시 **디스크** 스냅샷에서 진행 중이던 수업을 되살린다.

    원격은 여기서 건드리지 않는다. 기동 시점에는 어떤 사용자의 요청도 없어
    쓸 수 있는 토큰이 없고, 전부 긁어오려면 RLS를 우회하는 service_role 키가
    필요해지기 때문이다. 원격에만 있는 세션은 그 주인이 요청할 때 _get()이
    자기 토큰으로 되살린다 (지연 복구).
    """
    if _use_fake() or stateless():
        # 서버리스: 로컬 디스크가 비어 있다. 원격 세션은 주인이 요청할 때
        # _restore_one()이 되살린다 (지연 복구).
        return
    try:
        rows = DISK_STORE.load_all(newer_than=time.time() - SESSION_IDLE_TTL, limit=MAX_SESSIONS)
    except Exception:
        log.exception("session restore skipped (스냅샷 조회 실패)")
        return
    for sid, payload in rows:
        if len(SESSIONS) >= MAX_SESSIONS:
            break
        try:
            rec = _rebuild(sid, payload)
            if rec is None:
                _drop_snapshot(sid)
                continue
            SESSIONS[sid] = rec
            log.info("session restored: %s class=%s turn=%s", sid[:8],
                     rec.classroom.class_name, payload.get("snapshot", {}).get("state", {}).get("turn"))
        except (ClassroomError, ValueError, KeyError, OSError) as exc:
            # 학급·수업안이 사라진 경우 — 예상 가능한 상황이라 스택까지 남기지 않는다
            log.warning("session restore skipped: %s (%s)", sid[:8], exc)
            _drop_snapshot(sid)
        except Exception:
            log.exception("session restore failed: %s (스냅샷을 건너뜁니다)", sid[:8])


def _restore_one(sid: str, token: str | None) -> SessionRecord | None:
    """메모리에 없는 세션을 원격에서 하나만 되살린다 (지연 복구).

    다른 서버에서 진행하던 수업을 이어받는 경로다. 사용자 자신의 토큰으로
    조회하므로 RLS가 남의 세션을 막아 준다.
    """
    if _use_fake() or not hasattr(STORE, "load_one"):
        return None
    try:
        payload = STORE.load_one(sid, token=token)
    except Exception as exc:
        log.warning("session lazy restore failed: %s (%s)", sid[:8], exc)
        return None
    if not payload:
        return None
    try:
        rec = _rebuild(sid, payload, token)
    except Exception as exc:
        log.warning("session lazy restore skipped: %s (%s)", sid[:8], exc)
        return None
    if rec is None:
        return None
    _evict_stale()
    SESSIONS[sid] = rec
    log.info("session lazy-restored: %s class=%s", sid[:8], rec.classroom.class_name)
    return rec


def _classroom_id(req: "CreateSessionReq") -> str:
    """요청에서 학급 id를 뽑는다. 옛 클라이언트의 classroom_path도 받아 준다."""
    cid = (req.classroom_id or "").strip()
    if cid:
        return cid
    path = (req.classroom_path or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="학급을 선택해 주세요.")
    # "personas/class_6_3.json" → "sample:class_6_3"
    return "sample:" + Path(path).stem


def _classroom_of(meta: dict, token: str | None = None) -> Classroom:
    """스냅샷 meta에서 학급을 복원한다.

    스냅샷에 담긴 원본을 가장 먼저 쓴다. 그래야 수업 중에 학급을 지우거나
    고쳤어도 진행 중이던 수업은 시작할 때의 학생들 그대로 이어진다.
    """
    data = meta.get("classroom_data")
    if isinstance(data, dict):
        return parse_classroom(data, "학급")
    cid = meta.get("classroom_id")
    if cid:
        return LIBRARY.resolve(meta.get("user_id"), cid, token)[0]
    return load_classroom(ROOT / meta["classroom_path"])   # v0.6-3 이전 스냅샷


def _evict_stale() -> None:
    """TTL이 지났거나 상한을 넘긴 세션을 회수한다 (오래 쉰 것부터)."""
    now = time.time()
    with _SESSIONS_GUARD:
        for sid in [s for s, r in SESSIONS.items() if now - r.last_used > SESSION_IDLE_TTL]:
            SESSIONS.pop(sid, None)
            _drop_snapshot(sid)
            log.info("session evicted (idle TTL): %s", sid[:8])
        while len(SESSIONS) >= MAX_SESSIONS:
            oldest = min(SESSIONS, key=lambda s: SESSIONS[s].last_used)
            SESSIONS.pop(oldest, None)
            _drop_snapshot(oldest)
            log.info("session evicted (cap %d): %s", MAX_SESSIONS, oldest[:8])


# ---------------------------------------------------------------------------
# 인증 (Supabase Auth)
# ---------------------------------------------------------------------------

AUTH = _auth.load_config()
VERIFIER = _auth.Verifier(AUTH)
if AUTH.required:
    log.info("인증 활성 — 로그인한 사용자만 수업을 만들 수 있습니다 (%s)", AUTH.url)


def _public_base(request: Request) -> str:
    return (os.environ.get("CLASSROOM_SIM_PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _mcp_resource_metadata_url(request: Request) -> str:
    return f"{_public_base(request)}/.well-known/oauth-protected-resource/mcp"


def _current_user(request: Request) -> _auth.User | None:
    """요청의 Bearer 토큰에서 사용자를 확인한다.

    인증이 꺼져 있으면(LAN 전용 운영) None을 돌려주고 통과시킨다. 이때도 토큰이
    실려 오면 확인은 해 본다 — 켜고 끄는 과도기에 소유권 기록이 끊기지 않게.
    """
    token = _auth.bearer_token(request.headers.get("Authorization"))
    if not AUTH.required:
        if token and AUTH.can_verify:
            try:
                return VERIFIER.verify(token)
            except _auth.AuthError:
                return None
        return None
    try:
        return VERIFIER.verify(token)
    except _auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc),
                            headers={"WWW-Authenticate": "Bearer"}) from exc


def _who(request: Request) -> tuple[str | None, str | None]:
    """(user_id, access_token). RLS 모드에서는 토큰이 그대로 Supabase 인증에 쓰인다."""
    user = _current_user(request)
    return (user.id if user else None), _auth.bearer_token(request.headers.get("Authorization"))


def _get(session_id: str, user: _auth.User | None = None,
         token: str | None = None) -> SessionRecord:
    rec = SESSIONS.get(session_id)
    if rec is None:
        # 다른 서버에서 진행하던 수업일 수 있다 — 원격에서 하나만 되살려 본다
        rec = _restore_one(session_id, token)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="세션을 찾을 수 없습니다. 오래 자리를 비웠다면 세션이 회수되었을 수 있습니다 — 새 수업을 시작해 주세요.",
        )
    # 남의 수업에는 손대지 못한다. 존재 여부까지 숨기려고 403이 아닌 404로 답한다.
    owner = rec.user_id
    if AUTH.required and owner != (user.id if user else None):
        log.warning("session access denied: %s owner=%s requester=%s",
                    session_id[:8], (owner or "-")[:8], (user.id if user else "-")[:8])
        raise HTTPException(
            status_code=404,
            detail="세션을 찾을 수 없습니다. 오래 자리를 비웠다면 세션이 회수되었을 수 있습니다 — 새 수업을 시작해 주세요.",
        )
    rec.touch()
    rec.token = token          # RLS 모드에서 스냅샷을 쓸 때 이 토큰을 쓴다
    return rec


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------


def _safe_path(rel: str, subdir: str, suffix: str) -> Path:
    """저장소 루트 하위 경로만 허용 (경로 탈출 방지)."""
    if not rel:
        raise HTTPException(status_code=400, detail="경로가 비어 있습니다.")
    p = (ROOT / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    base = (ROOT / subdir).resolve()
    if base not in p.parents or p.suffix != suffix:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 경로입니다: {rel}")
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"파일이 없습니다: {rel}")
    return p


def _serialize(obj: Any) -> Any:
    """TurnResult 등 dataclass를 JSON 직렬화 가능한 형태로 변환."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _persona_cards(classroom: Classroom) -> list[dict]:
    """우측 상세 패널용 페르소나 요약 (계약 응답에 덧붙이는 부가 정보)."""
    cards = []
    for s in classroom.students:
        cards.append(
            {
                "id": s.id,
                "name": s.name,
                "achievement_level": s.achievement_level,
                "prior_knowledge": s.prior_knowledge,
                "learning_style": s.learning_style,
                "interests": list(s.interests),
                "personality": s.personality,
                "social": s.social,
                "notes": s.notes,
            }
        )
    return cards


# ---------------------------------------------------------------------------
# 앱
# ---------------------------------------------------------------------------

app = FastAPI(title="보이는 교실 — classroom_sim web", version="0.6")


# 서버리스에서는 codex를 쓸 수 없다 — codex CLI라는 하위 프로세스를 띄우는데
# 서버리스 런타임에는 그 실행 파일도, 로그인 상태도 없다.
ALLOWED_BACKENDS = ("mock", "anthropic") if stateless() else ("mock", "codex", "anthropic")
MAX_INPUT_CHARS = 2000       # 교사 입력 1회 상한
MAX_LESSON_BYTES = 200_000   # 수업안 파일 상한 (~200KB)
MAX_STUDENTS = 40            # 학급 인원 상한
MAX_TURNS_PER_SESSION = 200  # 세션당 턴 상한 (실수 루프·폭주로 인한 LLM 과금 방어)
TURNS_WARN_AT = 180          # 이 턴부터 상한 임박 안내
CREATE_RATE_LIMIT = 10       # 같은 주소에서 10분당 세션 생성 허용 횟수
CREATE_RATE_WINDOW = 600.0

_CREATE_TIMES: dict[str, list[float]] = {}
_CREATE_GUARD = threading.Lock()


def _check_create_rate(client_ip: str) -> None:
    """세션 생성 속도 제한 — 새로고침 루프·스크립트 폭주로부터 서버와 지갑을 지킨다."""
    now = time.time()
    with _CREATE_GUARD:
        times = [t for t in _CREATE_TIMES.get(client_ip, []) if now - t < CREATE_RATE_WINDOW]
        if len(times) >= CREATE_RATE_LIMIT:
            wait = int(CREATE_RATE_WINDOW - (now - times[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"수업 생성이 너무 잦습니다. 약 {max(1, wait // 60)}분 후 다시 시도해 주세요.")
        times.append(now)
        _CREATE_TIMES[client_ip] = times


class CreateSessionReq(BaseModel):
    lesson_path: str
    classroom_id: str = ""       # "sample:class_6_3" 또는 내 학급의 uuid
    classroom_path: str = ""     # 옛 클라이언트 호환 — "personas/class_6_3.json"
    backend: str = "mock"
    seed: int | None = None


class CreateClassroomReq(BaseModel):
    json_text: str


class TurnReq(BaseModel):
    input: str


@app.get("/")
def index() -> FileResponse:
    path = STATIC_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=500, detail="index.html이 없습니다.")
    return FileResponse(path)


@app.get("/oauth/consent")
def oauth_consent() -> FileResponse:
    return index()


@app.get("/api/classrooms")
def list_classrooms(request: Request) -> list[dict]:
    """내 학급(위) + 샘플 학급(아래) → [{id, class_name, grade, count, mine}]"""
    uid, token = _who(request)      # 로그인 강제 시 학급 목록도 열람 불가
    return LIBRARY.list(uid, token)


@app.post("/api/classrooms", status_code=201)
def create_classroom(req: CreateClassroomReq, request: Request) -> dict:
    """교사가 붙여넣거나 올린 학급 JSON을 검증해 저장한다."""
    uid, token = _who(request)
    try:
        return LIBRARY.create(uid, req.json_text or "", token)
    except (ClassroomError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/classrooms/{classroom_id}")
def delete_classroom(classroom_id: str, request: Request) -> dict:
    uid, token = _who(request)
    try:
        LIBRARY.delete(uid, classroom_id, token)
    except ClassroomError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": classroom_id}


# ---------------------------------------------------------------------------
# MCP — ChatGPT가 직접 무대를 진행하는 경로 (web/mcp.py)
# ---------------------------------------------------------------------------

MCP = _mcp.McpServer(LIBRARY, REPORTS, _incidents)


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP streamable HTTP 엔드포인트 (JSON-RPC 2.0).

    ChatGPT 개발자 모드에 이 주소를 등록하면 도구 7종이 노출된다.
    인증은 웹판과 같은 Bearer 토큰을 쓴다.
    """
    try:
        uid, token = _who(request)
    except HTTPException as exc:
        if exc.status_code == 401 and AUTH.required:
            headers = dict(exc.headers or {})
            headers["WWW-Authenticate"] = (
                f'Bearer resource_metadata="{_mcp_resource_metadata_url(request)}"'
            )
            raise HTTPException(status_code=401, detail=exc.detail, headers=headers) from exc
        raise
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_mcp._error(None, -32700, "JSON을 해석하지 못했습니다."), status_code=400)

    if isinstance(body, list):                      # 일괄 요청
        out = [r for r in (_mcp.handle(b, MCP, uid, token) for b in body) if r is not None]
        return JSONResponse(out) if out else Response(status_code=202)
    res = _mcp.handle(body, MCP, uid, token)
    if res is None:                                 # 알림에는 본문 없이 202
        return Response(status_code=202)
    return JSONResponse(res)


@app.get("/mcp")
def mcp_info() -> dict:
    """브라우저로 열어 봤을 때의 안내 (MCP 자체는 POST를 쓴다)."""
    return {"server": _mcp.SERVER_INFO, "protocolVersion": _mcp.PROTOCOL_VERSION,
            "transport": "streamable-http (POST /mcp)",
            "tools": [t["name"] for t in _mcp.TOOLS],
            "auth": "required" if AUTH.required else "open",
            "docs": "docs/specs/v0.6_chatgpt_app.md"}


@app.get("/.well-known/oauth-protected-resource/mcp")
def mcp_oauth_resource(request: Request) -> dict:
    return {
        "resource": f"{_public_base(request)}/mcp",
        "authorization_servers": [f"{AUTH.url}/auth/v1"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "email"],
    }


@app.get("/api/reports")
def list_reports(request: Request) -> list[dict]:
    """지난 수업 기록 목록 (본문 없이 요약만)."""
    uid, token = _who(request)
    return REPORTS.list(uid, token)


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, request: Request) -> dict:
    uid, token = _who(request)
    try:
        return REPORTS.get(uid, report_id, token)
    except ReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str, request: Request) -> dict:
    uid, token = _who(request)
    try:
        REPORTS.delete(uid, report_id, token)
    except ReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": report_id}


@app.get("/api/dimensions")
def list_dimensions(request: Request) -> dict:
    """학급 만들기 폼이 쓰는 속성 카탈로그 (personas/schema/dimensions.json).

    9그룹 102속성. 폼은 values가 있으면 선택지로, 없으면 자유 입력으로 그린다.
    """
    _current_user(request)
    f = ROOT / "personas" / "schema" / "dimensions.json"
    if not f.is_file():
        return {"version": "", "groups": []}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        log.exception("dimensions.json 을 읽지 못했습니다")
        return {"version": "", "groups": []}


@app.get("/api/lessons")
def list_lessons(request: Request) -> list[dict]:
    """lessons/*.md 스캔 → [{path, title}]"""
    _current_user(request)
    out: list[dict] = []
    for p in sorted((ROOT / "lessons").glob("*.md")):
        title = p.stem
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("#"):
                    title = line.lstrip("#").strip()
                    break
        except Exception:
            pass
        out.append({"path": str(p.relative_to(ROOT)), "title": title})
    return out


@app.get("/api/auth/config")
def auth_config() -> dict:
    """로그인 화면이 필요로 하는 값. anon 키는 공개용이라 내려보내도 안전하다."""
    return {
        "required": AUTH.required,
        "url": AUTH.url if AUTH.required else "",
        "anon_key": AUTH.anon_key if AUTH.required else "",
    }


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    """토큰이 아직 유효한지 확인 (로그인 화면을 건너뛸지 판단)."""
    user = _current_user(request)
    if user is None:
        return {"authenticated": False, "required": AUTH.required}
    return {"authenticated": True, "required": AUTH.required,
            "user_id": user.id, "email": user.email}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """브라우저가 관성적으로 요청하는 /favicon.ico — 404 콘솔 노이즈 방지."""
    icon = STATIC_DIR / "favicon.png"
    if not icon.is_file():
        raise HTTPException(status_code=404, detail="favicon 없음")
    return FileResponse(str(icon), media_type="image/png")


@app.get("/healthz")
def healthz() -> dict:
    """운영 확인용 — 프로세스 생존, 세션 수, 가동 시간. LLM은 호출하지 않는다."""
    return {
        "status": "ok",
        "version": app.version,
        "uptime_s": int(time.time() - START_TIME),
        "sessions": len(SESSIONS),
        "max_sessions": MAX_SESSIONS,
        "store": STORE.name,          # disk / disk+supabase — 배포 후 설정이 먹었는지 확인용
        "auth": "required" if AUTH.required else "open",
        "remote_auth": (remote_config().describe() if remote_config() else "none"),
        "mode": "serverless" if stateless() else "server",
        "backends": list(ALLOWED_BACKENDS),
    }


@app.post("/api/sessions")
def create_session(req: CreateSessionReq, request: Request) -> dict:
    user = _current_user(request)
    token = _auth.bearer_token(request.headers.get("Authorization"))
    _check_create_rate(user.id if user else (request.client.host if request.client else "unknown"))
    if req.backend not in ALLOWED_BACKENDS:
        raise HTTPException(status_code=400,
                            detail=f"지원하지 않는 백엔드입니다: {req.backend!r} (가능: {', '.join(ALLOWED_BACKENDS)})")
    lpath = _safe_path(req.lesson_path, "lessons", ".md")
    cid = _classroom_id(req)
    try:
        classroom, classroom_data = LIBRARY.resolve(user.id if user else None, cid, token)
    except (ClassroomError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"학급 로드 실패: {exc}") from exc
    if len(classroom.students) > MAX_STUDENTS:
        raise HTTPException(status_code=400,
                            detail=f"학급 인원이 너무 많습니다 ({len(classroom.students)}명). 최대 {MAX_STUDENTS}명까지 지원합니다.")
    if lpath.stat().st_size > MAX_LESSON_BYTES:
        raise HTTPException(status_code=400,
                            detail="수업안 파일이 너무 큽니다 (200KB 초과). 핵심 내용만 남겨 주세요.")
    lesson_text = lpath.read_text(encoding="utf-8")

    _evict_stale()
    session, backend_used = _make_session(classroom, lesson_text, req.backend, req.seed)
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = SessionRecord(
        session,
        classroom,
        {
            "classroom_id": cid,
            # 학급 원본을 함께 남긴다 — 수업 중에 학급을 지우거나 고쳐도
            # 진행 중이던 수업은 시작할 때의 학생들로 되살아나야 한다.
            "classroom_data": classroom_data,
            "lesson_path": str(lpath.relative_to(ROOT)),
            "backend": backend_used,
            "class_name": classroom.class_name,
            "user_id": user.id if user else None,
        },
    )
    SESSIONS[sid].token = token
    log.info("session created: %s class=%s students=%d backend=%s lesson=%s",
             sid[:8], classroom.class_name, len(classroom.students), backend_used, lpath.name)
    _persist_session(sid, SESSIONS[sid])
    snapshot = _serialize(session.state_snapshot())
    return {
        "session_id": sid,
        **snapshot,
        # 부가 정보 (계약 필드는 그대로 유지)
        "backend": backend_used,
        "lesson_title": _title_of(lpath),
        "personas": _persona_cards(classroom),
    }


def _title_of(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
    except Exception:
        pass
    return path.stem


def _save_report(rec: "SessionRecord", session_id: str, report: str) -> tuple[str | None, str | None]:
    """리포트·전사를 서버에 남긴다 (브라우저를 닫아도 유실되지 않게).

    (표시용 파일 경로, 기록 id)를 돌려준다. 실패해도 응답은 막지 않는다 —
    교사는 이미 화면에서 리포트를 보고 있고, 내려받을 수도 있다.
    """
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cname = re.sub(r"[^\w가-힣-]+", "_", rec.classroom.class_name).strip("_") or "학급"
        base = f"{stamp}_{cname}_{session_id[:8]}"
        try:
            transcript = _serialize(rec.session.transcript_json())
        except Exception:
            transcript = []
        state = getattr(rec.session, "state", None)
        rid = REPORTS.save({
            "user_id": rec.user_id or "",
            "session_id": session_id,
            "class_name": rec.classroom.class_name,
            "lesson_title": _title_of(ROOT / rec.meta["lesson_path"]) if rec.meta.get("lesson_path") else "",
            "turns": int(getattr(state, "turn", 0) or 0),
            "minutes": int(getattr(state, "minute", 0) or 0),
        }, report or "", transcript, base, rec.token)
        log.info("report saved: session=%s path=%s id=%s", session_id[:8], f"{base}.md", rid[:8])
        return f"reports/stage/{base}.md", rid
    except Exception:
        log.exception("report save failed: session=%s", session_id[:8])
        return None, None


@app.post("/api/sessions/{session_id}/turn")
def take_turn(session_id: str, req: TurnReq, request: Request) -> dict:
    rec = _get(session_id, _current_user(request), _auth.bearer_token(request.headers.get('Authorization')))
    text = (req.input or "").strip()
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(status_code=400,
                            detail=f"입력이 너무 깁니다 ({len(text)}자). 한 번에 {MAX_INPUT_CHARS}자 이내로 나눠 말해 주세요.")
    # 턴 상한 — LLM 백엔드 폭주 과금 방어. /종료·/상태는 LLM을 쓰지 않으므로 허용.
    cur_turn = int(getattr(getattr(rec.session, "state", None), "turn", 0) or 0)
    if cur_turn >= MAX_TURNS_PER_SESSION and not re.match(r"^/(종료|상태)(\s|$)", text):
        raise HTTPException(
            status_code=429,
            detail=f"이 수업이 턴 상한({MAX_TURNS_PER_SESSION}턴)에 도달했습니다. "
                   "/종료 로 리포트를 만들고 새 수업으로 시작해 주세요.")
    if not rec.lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="이전 입력이 아직 처리 중입니다. 잠시 후 다시 보내 주세요.")
    t0 = time.perf_counter()
    try:
        result = rec.session.turn(text)
    except Exception as exc:
        # 내부 예외 문자열을 사용자에게 그대로 노출하지 않는다 (서버 로그로만)
        log.exception("turn failed: session=%s input=%r", session_id[:8], text[:80])
        raise HTTPException(status_code=500,
                            detail="턴 처리 중 서버 오류가 발생했습니다. 같은 입력을 한 번 더 보내 보시고, 반복되면 새 수업으로 시작해 주세요.") from exc
    finally:
        rec.touch()
        rec.lock.release()
    log.info("turn ok: session=%s turn=%d took=%.1fs events=%d ended=%s",
             session_id[:8], getattr(result, "turn", -1), time.perf_counter() - t0,
             len(getattr(result, "events", []) or []), getattr(result, "ended", False))
    out = _serialize(result)
    new_turn = int(getattr(result, "turn", 0) or 0)
    if TURNS_WARN_AT <= new_turn < MAX_TURNS_PER_SESSION:
        out["notice"] = (f"수업이 {new_turn}턴째입니다. {MAX_TURNS_PER_SESSION}턴에 도달하면 "
                         "새 입력이 제한되니 /종료 로 리포트를 만들어 주세요.")
    if getattr(result, "ended", False):
        _drop_snapshot(session_id, rec.token)   # 종료된 수업은 리포트로 남으므로 스냅샷은 정리
        if getattr(result, "report_markdown", None):
            out["report_saved_path"], out["report_id"] = _save_report(rec, session_id, result.report_markdown)
    else:
        if not _persist_session(session_id, rec) and stateless():
            # 서버리스에서 저장이 안 되면 이 턴이 마지막으로 남는 기록이다.
            # 교사가 모르고 계속 진행했다가 통째로 잃는 것보다 지금 아는 편이 낫다.
            out["notice"] = ("⚠️ 이번 턴을 저장하지 못했습니다. 지금 [전사 내려받기]로 "
                             "기록을 남기고, 잠시 후 다시 시도해 주세요. "
                             "(저장소 연결을 확인해야 할 수 있습니다)")
    return out


@app.get("/api/sessions/{session_id}/state")
def get_state(session_id: str, request: Request) -> dict:
    rec = _get(session_id, _current_user(request), _auth.bearer_token(request.headers.get('Authorization')))
    snap = _serialize(rec.session.state_snapshot())
    # 새로고침 복구용 부가 정보 (계약 필드는 유지한 채 덧붙임)
    snap["personas"] = _persona_cards(rec.classroom)
    snap["backend"] = rec.meta.get("backend", "")
    lp = rec.meta.get("lesson_path")
    snap["lesson_title"] = _title_of(ROOT / lp) if lp else ""
    return snap


@app.get("/api/sessions/{session_id}/transcript")
def get_transcript(session_id: str, request: Request) -> list[dict]:
    rec = _get(session_id, _current_user(request), _auth.bearer_token(request.headers.get('Authorization')))
    return _serialize(rec.session.transcript_json())


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: str, request: Request) -> dict:
    rec = _get(session_id, _current_user(request), _auth.bearer_token(request.headers.get('Authorization')))
    if not rec.lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="이전 입력이 아직 처리 중입니다. 잠시 후 다시 시도해 주세요.")
    try:
        report = rec.session.end()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"종료 처리 실패: {exc}") from exc
    finally:
        rec.touch()
        rec.lock.release()
    _drop_snapshot(session_id, rec.token)
    saved_path, rid = _save_report(rec, session_id, report)
    return {"report_markdown": report, "report_saved_path": saved_path, "report_id": rid}


# 정적 파일 (앱 라우트 뒤에 마운트해야 /api 경로를 가리지 않는다)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 기동 시 디스크 스냅샷에서 진행 중이던 수업 복구
_restore_sessions()
