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

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..personas import Classroom, load_classroom

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

    def touch(self) -> None:
        self.last_used = time.time()


SESSIONS: dict[str, SessionRecord] = {}
_SESSIONS_GUARD = threading.Lock()


def _evict_stale() -> None:
    """TTL이 지났거나 상한을 넘긴 세션을 회수한다 (오래 쉰 것부터)."""
    now = time.time()
    with _SESSIONS_GUARD:
        for sid in [s for s, r in SESSIONS.items() if now - r.last_used > SESSION_IDLE_TTL]:
            SESSIONS.pop(sid, None)
            log.info("session evicted (idle TTL): %s", sid[:8])
        while len(SESSIONS) >= MAX_SESSIONS:
            oldest = min(SESSIONS, key=lambda s: SESSIONS[s].last_used)
            SESSIONS.pop(oldest, None)
            log.info("session evicted (cap %d): %s", MAX_SESSIONS, oldest[:8])


def _get(session_id: str) -> SessionRecord:
    rec = SESSIONS.get(session_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="세션을 찾을 수 없습니다. 오래 자리를 비웠다면 세션이 회수되었을 수 있습니다 — 새 수업을 시작해 주세요.",
        )
    rec.touch()
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

app = FastAPI(title="보이는 교실 — classroom_sim web", version="0.5")


ALLOWED_BACKENDS = ("mock", "codex", "anthropic")
MAX_INPUT_CHARS = 2000       # 교사 입력 1회 상한
MAX_LESSON_BYTES = 200_000   # 수업안 파일 상한 (~200KB)
MAX_STUDENTS = 40            # 학급 인원 상한


class CreateSessionReq(BaseModel):
    classroom_path: str
    lesson_path: str
    backend: str = "mock"
    seed: int | None = None


class TurnReq(BaseModel):
    input: str


@app.get("/")
def index() -> FileResponse:
    path = STATIC_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=500, detail="index.html이 없습니다.")
    return FileResponse(path)


@app.get("/api/classrooms")
def list_classrooms() -> list[dict]:
    """personas/*.json 스캔 → [{path, class_name, grade, count}]"""
    out: list[dict] = []
    for p in sorted((ROOT / "personas").glob("*.json")):
        try:
            c = load_classroom(p)
        except Exception:
            continue
        out.append(
            {
                "path": str(p.relative_to(ROOT)),
                "class_name": c.class_name,
                "grade": c.grade,
                "count": len(c.students),
            }
        )
    return out


@app.get("/api/lessons")
def list_lessons() -> list[dict]:
    """lessons/*.md 스캔 → [{path, title}]"""
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


@app.get("/healthz")
def healthz() -> dict:
    """운영 확인용 — 프로세스 생존, 세션 수, 가동 시간. LLM은 호출하지 않는다."""
    return {
        "status": "ok",
        "version": app.version,
        "uptime_s": int(time.time() - START_TIME),
        "sessions": len(SESSIONS),
        "max_sessions": MAX_SESSIONS,
    }


@app.post("/api/sessions")
def create_session(req: CreateSessionReq) -> dict:
    if req.backend not in ALLOWED_BACKENDS:
        raise HTTPException(status_code=400,
                            detail=f"지원하지 않는 백엔드입니다: {req.backend!r} (가능: {', '.join(ALLOWED_BACKENDS)})")
    cpath = _safe_path(req.classroom_path, "personas", ".json")
    lpath = _safe_path(req.lesson_path, "lessons", ".md")
    try:
        classroom = load_classroom(cpath)
    except Exception as exc:
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
            "classroom_path": str(cpath.relative_to(ROOT)),
            "lesson_path": str(lpath.relative_to(ROOT)),
            "backend": backend_used,
        },
    )
    log.info("session created: %s class=%s students=%d backend=%s lesson=%s",
             sid[:8], classroom.class_name, len(classroom.students), backend_used, lpath.name)
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


def _save_report(rec: "SessionRecord", session_id: str, report: str) -> str | None:
    """리포트·전사를 서버에도 남긴다 (브라우저를 닫아도 유실되지 않게). 실패해도 응답은 막지 않는다."""
    try:
        out_dir = ROOT / "reports" / "stage"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cname = re.sub(r"[^\w가-힣-]+", "_", rec.classroom.class_name).strip("_") or "학급"
        base = f"{stamp}_{cname}_{session_id[:8]}"
        (out_dir / f"{base}.md").write_text(report or "", encoding="utf-8")
        try:
            transcript = rec.session.transcript_json()
            (out_dir / f"{base}.transcript.json").write_text(
                json.dumps(_serialize(transcript), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        log.info("report saved: session=%s path=%s", session_id[:8], f"{base}.md")
        return str((out_dir / f"{base}.md").relative_to(ROOT))
    except Exception:
        log.exception("report save failed: session=%s", session_id[:8])
        return None


@app.post("/api/sessions/{session_id}/turn")
def take_turn(session_id: str, req: TurnReq) -> dict:
    rec = _get(session_id)
    text = (req.input or "").strip()
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(status_code=400,
                            detail=f"입력이 너무 깁니다 ({len(text)}자). 한 번에 {MAX_INPUT_CHARS}자 이내로 나눠 말해 주세요.")
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
    if getattr(result, "ended", False) and getattr(result, "report_markdown", None):
        out["report_saved_path"] = _save_report(rec, session_id, result.report_markdown)
    return out


@app.get("/api/sessions/{session_id}/state")
def get_state(session_id: str) -> dict:
    rec = _get(session_id)
    snap = _serialize(rec.session.state_snapshot())
    # 새로고침 복구용 부가 정보 (계약 필드는 유지한 채 덧붙임)
    snap["personas"] = _persona_cards(rec.classroom)
    snap["backend"] = rec.meta.get("backend", "")
    lp = rec.meta.get("lesson_path")
    snap["lesson_title"] = _title_of(ROOT / lp) if lp else ""
    return snap


@app.get("/api/sessions/{session_id}/transcript")
def get_transcript(session_id: str) -> list[dict]:
    rec = _get(session_id)
    return _serialize(rec.session.transcript_json())


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: str) -> dict:
    rec = _get(session_id)
    if not rec.lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="이전 입력이 아직 처리 중입니다. 잠시 후 다시 시도해 주세요.")
    try:
        report = rec.session.end()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"종료 처리 실패: {exc}") from exc
    finally:
        rec.touch()
        rec.lock.release()
    return {"report_markdown": report, "report_saved_path": _save_report(rec, session_id, report)}


# 정적 파일 (앱 라우트 뒤에 마운트해야 /api 경로를 가리지 않는다)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
