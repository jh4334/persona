# 교실 무대 엔진 — 인터페이스 계약 (v0.3~v0.5)

엔진 구현(`src/classroom_sim/stage/`)과 웹 구현(`src/classroom_sim/web/`)이 공유하는 계약.
**양쪽 모두 이 시그니처를 그대로 따른다. 임의 변경 금지.**

## 데이터 모델 (`stage/state.py`)

```python
from dataclasses import dataclass, field

@dataclass
class StudentState:
    comprehension: int = 60   # 이해도 0~100
    interest: int = 60        # 흥미 0~100
    focus: int = 70           # 집중 0~100
    emotion: str = "평온"      # 평온|들뜸|위축|불안|지루함|몰입 등 자유
    visible_action: str = ""  # 현재 겉으로 보이는 모습 (짧은 서술, 예: "창밖을 봄")

@dataclass
class TurnEvent:
    actor: str      # "교사" | 학생 id (예: "S04") | "무대"
    kind: str       # teacher_say|teacher_action|student_say|student_action|narration|system
    content: str    # 발화 내용 또는 행동/서술

@dataclass
class TurnResult:
    turn: int
    events: list[TurnEvent]              # 이번 턴에 새로 발생한 이벤트 (표시용)
    states: dict[str, StudentState]      # 학생 id → 최신 상태 (전체)
    minute: int                          # 수업 경과 분
    phase: str                           # 도입|전개|활동|모둠활동|정리|종료 등
    ended: bool = False
    report_markdown: str | None = None   # /종료 시 사후 리포트
```

## 백엔드 (`stage/backend.py`)

```python
class LLMBackend(Protocol):
    def complete_json(self, *, system, messages: list[dict], schema: dict, max_tokens: int = 2048) -> dict: ...
    def complete_text(self, *, system, messages: list[dict], max_tokens: int = 2048) -> str: ...

def make_backend(name: str) -> LLMBackend
# "anthropic" → Claude API (감독: claude-haiku-4-5, 학생/분석: claude-opus-5 — 생성자 인자로 오버라이드 가능)
# "mock"      → API 키 없이 동작하는 결정적 규칙 기반 백엔드 (데모·테스트·CI용)
```

`system` 인자는 str 또는 content 블록 리스트(캐싱용) 모두 허용.

## 세션 (`stage/session.py`)

```python
class StageSession:
    def __init__(self, classroom: Classroom, lesson_text: str,
                 backend: LLMBackend, seed: int | None = None): ...

    def turn(self, teacher_input: str) -> TurnResult
    def state_snapshot(self) -> dict   # 아래 JSON 형태
    def transcript_json(self) -> list[dict]
    def end(self) -> str               # 사후 리포트 마크다운 반환 (turn("/종료")와 동일 효과)
```

`state_snapshot()` 반환 형태 (웹 API가 그대로 직렬화):

```json
{
  "turn": 7, "minute": 18, "phase": "전개", "ended": false,
  "class_name": "가상초등학교 6학년 3반",
  "students": [
    {"id": "S01", "name": "김하늘", "achievement_level": "상",
     "comprehension": 90, "interest": 45, "focus": 50,
     "emotion": "지루함", "visible_action": "샤프를 돌리고 있음"}
  ]
}
```

## 교사 입력 문법 (session.turn이 파싱)

| 입력 | 의미 | LLM 호출 |
|---|---|---|
| (일반 텍스트) | 전체 발화 | 감독 1 + 발화자 n |
| `@이름 텍스트` 또는 `@S04 텍스트` | 특정 학생 지목 (해당 학생 반드시 발화) | 감독 1 + 발화자 n |
| `/판서 텍스트` | 판서/자료 제시 | 감독 1 (+발화자) |
| `/활동 지시문` | 활동 국면 전환 | 감독 1 (+발화자) |
| `/모둠 4인` 또는 `/모둠 S01,S04/S02,S05` | 모둠 편성 (자동/수동) | 감독 1 |
| `/모둠활동 지시문` | 모둠 내 학생끼리 대화 1라운드 (모둠별 2~3발화) | 감독 1 + 모둠별 1 |
| `/순회 이름 [말걸기]` | 1:1 순회 지도 장면 | 감독 1 + 해당 학생 1 |
| `/칭찬 이름 [텍스트]`, `/주의 이름 [텍스트]` | 개별 피드백 | 감독 1 (+해당 학생) |
| `/시간 N분` | 시간 경과 (활동 결과 요약) | 감독 1 |
| `/돌발 [카드명]` | 돌발 상황 주입 (카드명 없으면 무작위) | 감독 1 (+발화자) |
| `/상태` | 상태표만 반환 | **0회** |
| `/종료` | 수업 종료 → 사후 리포트 + 수업 분석 | 분석 1~2회 |

잘못된 명령은 예외 대신 `TurnEvent(actor="무대", kind="system", content="안내...")`로 응답.

## 돌발 카드 (`stage/incidents.py`)

최소 6종: 친구갈등, 기기고장, 방송소음, 조퇴요청, 벌레소동, 복도소란.
`draw(name=None) -> Incident(name, description)`.

## 수업 분석 (`stage/analysis.py`) — v0.5

`analyze(transcript_json, classroom) -> str` (마크다운):
- 결정적 통계: 교사/학생 발화 수, 학생별 발언 횟수·형평성, 지목 분포, 질문(물음표) 수
- LLM 1회: 발문 수준 분류(사실확인/절차/원리), 개선 제안 (mock 백엔드는 고정 문구)

## 웹 API (`web/server.py`) — FastAPI

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/` | — | 정적 index.html |
| GET | `/api/classrooms` | — | `[{path, class_name, grade, count}]` (personas/*.json 스캔) |
| GET | `/api/lessons` | — | `[{path, title}]` (lessons/*.md 스캔) |
| POST | `/api/sessions` | `{classroom_path, lesson_path, backend}` | `{session_id}` + snapshot |
| POST | `/api/sessions/{id}/turn` | `{input}` | TurnResult 직렬화 (events, states, minute, phase, ended, report_markdown) |
| GET | `/api/sessions/{id}/state` | — | state_snapshot |
| GET | `/api/sessions/{id}/transcript` | — | transcript_json |
| POST | `/api/sessions/{id}/end` | — | `{report_markdown}` |

세션은 메모리 dict 보관(프로토타입). 직렬화는 dataclasses.asdict 기반.

## 경로 소유권

- 엔진 에이전트: `src/classroom_sim/stage/**` 만 수정
- 웹 에이전트: `src/classroom_sim/web/**` 만 수정 (정적 파일 포함: `src/classroom_sim/web/static/`)
- 공용 파일(requirements.txt, README 등)은 통합 담당(메인 세션)이 수정
