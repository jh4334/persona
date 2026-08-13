"""교실 무대 엔진 (v0.3~v0.5).

교사가 한 마디씩 수업을 진행하면 학생 페르소나가 실시간으로 반응하는
인터랙티브 시뮬레이션 엔진. 무대 감독 패턴으로 턴당 LLM 호출을 억제한다.

사용 예:
    from classroom_sim.personas import load_classroom
    from classroom_sim.stage import StageSession, make_backend

    session = StageSession(load_classroom("personas/class_6_3.json"),
                           lesson_text, make_backend("mock"), seed=7)
    result = session.turn("@최민준 3 대 5에서 기준량이 뭘까?")
"""

from .analysis import analyze
from .backend import (
    AnthropicBackend,
    BackendError,
    LLMBackend,
    MockBackend,
    make_backend,
)
from .incidents import CARDS, Incident, draw
from .session import StageSession
from .state import ClassState, StudentState, TurnEvent, TurnResult
from .transcript import Transcript, TranscriptEntry

__all__ = [
    "StageSession",
    "StudentState",
    "TurnEvent",
    "TurnResult",
    "ClassState",
    "Transcript",
    "TranscriptEntry",
    "LLMBackend",
    "AnthropicBackend",
    "MockBackend",
    "BackendError",
    "make_backend",
    "Incident",
    "CARDS",
    "draw",
    "analyze",
]
