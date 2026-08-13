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
import os
import uuid
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


class SessionRecord:
    def __init__(self, session: Any, classroom: Classroom, meta: dict) -> None:
        self.session = session
        self.classroom = classroom
        self.meta = meta


SESSIONS: dict[str, SessionRecord] = {}


def _get(session_id: str) -> SessionRecord:
    rec = SESSIONS.get(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
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


@app.post("/api/sessions")
def create_session(req: CreateSessionReq) -> dict:
    cpath = _safe_path(req.classroom_path, "personas", ".json")
    lpath = _safe_path(req.lesson_path, "lessons", ".md")
    try:
        classroom = load_classroom(cpath)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"학급 로드 실패: {exc}") from exc
    lesson_text = lpath.read_text(encoding="utf-8")

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


@app.post("/api/sessions/{session_id}/turn")
def take_turn(session_id: str, req: TurnReq) -> dict:
    rec = _get(session_id)
    try:
        result = rec.session.turn(req.input)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"턴 처리 실패: {exc}") from exc
    return _serialize(result)


@app.get("/api/sessions/{session_id}/state")
def get_state(session_id: str) -> dict:
    rec = _get(session_id)
    return _serialize(rec.session.state_snapshot())


@app.get("/api/sessions/{session_id}/transcript")
def get_transcript(session_id: str) -> list[dict]:
    rec = _get(session_id)
    return _serialize(rec.session.transcript_json())


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: str) -> dict:
    rec = _get(session_id)
    try:
        report = rec.session.end()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"종료 처리 실패: {exc}") from exc
    return {"report_markdown": report}


# 정적 파일 (앱 라우트 뒤에 마운트해야 /api 경로를 가리지 않는다)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
