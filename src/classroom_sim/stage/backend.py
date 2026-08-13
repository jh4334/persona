"""LLM 백엔드 추상화.

- AnthropicBackend: Claude API (감독=저비용 모델, 학생/분석=고품질 모델)
- MockBackend: API 키 없이 완전히 동작하는 결정적 규칙 기반 백엔드 (데모·테스트·CI용)

`anthropic` 패키지는 AnthropicBackend 안에서 지연 import 하므로, mock만 쓸 때는
SDK가 설치되어 있지 않아도 동작한다.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Protocol, runtime_checkable

FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_DIRECTOR_MODEL = "claude-haiku-4-5"
DEFAULT_ACTOR_MODEL = "claude-opus-5"

# 감독/학생 요청에 구조화 데이터를 실어 보내는 태그.
# 실제 LLM에게는 읽기 쉬운 근거 자료가 되고, MockBackend는 이 블록을 파싱해 규칙을 적용한다.
PAYLOAD_OPEN = "<무대_데이터>"
PAYLOAD_CLOSE = "</무대_데이터>"


class BackendError(RuntimeError):
    """백엔드 호출 실패(거부 포함)."""


@runtime_checkable
class LLMBackend(Protocol):
    def complete_json(
        self,
        *,
        system: Any,
        messages: list[dict],
        schema: dict,
        max_tokens: int = 2048,
        model_role: str = "actor",
    ) -> dict: ...

    def complete_text(
        self,
        *,
        system: Any,
        messages: list[dict],
        max_tokens: int = 2048,
        model_role: str = "actor",
    ) -> str: ...


# --------------------------------------------------------------------------
# 페이로드 헬퍼
# --------------------------------------------------------------------------

def pack_payload(obj: dict) -> str:
    """구조화 데이터를 프롬프트에 실을 수 있는 텍스트 블록으로 만든다."""
    return f"{PAYLOAD_OPEN}\n{json.dumps(obj, ensure_ascii=False, indent=1)}\n{PAYLOAD_CLOSE}"


def _message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def extract_payload(messages: list[dict]) -> dict:
    """메시지에서 마지막 무대_데이터 블록을 파싱한다(없으면 빈 dict)."""
    for message in reversed(messages):
        text = _message_text(message)
        start = text.find(PAYLOAD_OPEN)
        end = text.rfind(PAYLOAD_CLOSE)
        if start >= 0 and end > start:
            raw = text[start + len(PAYLOAD_OPEN):end].strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
    return {}


# --------------------------------------------------------------------------
# Anthropic 백엔드
# --------------------------------------------------------------------------

class AnthropicBackend:
    """Claude API 백엔드. 감독 호출과 배우(학생/분석) 호출에 다른 모델을 쓴다."""

    supports_cache = True

    def __init__(
        self,
        director_model: str = DEFAULT_DIRECTOR_MODEL,
        actor_model: str = DEFAULT_ACTOR_MODEL,
    ) -> None:
        self.director_model = director_model
        self.actor_model = actor_model
        self._client = None  # 지연 생성

    # -- 내부 --

    def _client_or_create(self):
        if self._client is None:
            import anthropic  # 지연 import: mock만 쓸 때 SDK 불필요

            self._client = anthropic.Anthropic()
        return self._client

    def _model(self, model_role: str) -> str:
        return self.director_model if model_role == "director" else self.actor_model

    @staticmethod
    def _text_of(response) -> str:
        return next((b.text for b in response.content if b.type == "text"), "")

    # -- 공개 API --

    def complete_json(
        self,
        *,
        system: Any,
        messages: list[dict],
        schema: dict,
        max_tokens: int = 2048,
        model_role: str = "actor",
    ) -> dict:
        response = self._client_or_create().beta.messages.create(
            model=self._model(model_role),
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=messages,
        )
        if response.stop_reason == "refusal":
            raise BackendError("요청이 안전상의 이유로 거부되었습니다 (refusal).")
        try:
            return json.loads(self._text_of(response))
        except json.JSONDecodeError as e:  # 방어적 처리
            raise BackendError(f"JSON 파싱 실패: {e}") from e

    def complete_text(
        self,
        *,
        system: Any,
        messages: list[dict],
        max_tokens: int = 2048,
        model_role: str = "actor",
    ) -> str:
        response = self._client_or_create().beta.messages.create(
            model=self._model(model_role),
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            messages=messages,
        )
        if response.stop_reason == "refusal":
            raise BackendError("요청이 안전상의 이유로 거부되었습니다 (refusal).")
        return self._text_of(response)


# --------------------------------------------------------------------------
# Mock 백엔드 (규칙 기반, 결정적)
# --------------------------------------------------------------------------

# 집중이 무너졌을 때 겉으로 드러나는 모습
_IDLE_ACTIONS = (
    "창밖을 보고 있음",
    "샤프를 돌리고 있음",
    "책상에 엎드릴 듯 몸을 기울임",
    "옆 친구에게 말을 걸고 있음",
    "지우개를 만지작거림",
    "공책 귀퉁이에 낙서 중",
)

_ANXIOUS_TRAITS = ("발표 불안", "발표불안", "내성적", "위축", "자신감이 낮", "시험불안", "긴장")
_ACTIVE_TRAITS = ("자발적", "적극", "발표를 즐", "질문이 많", "호기심", "활발", "승부욕")

# 성취수준별 이해도 드리프트 계수
_LEVEL_DRIFT = {"상": 1.0, "중상": 0.5, "중": -0.2, "하": -2.0}

# 교사 행동별 기본 소요 시간(분)
_MINUTE_COST = {
    "teacher_say": 1,
    "nominate": 1,
    "board": 2,
    "activity": 3,
    "group_form": 2,
    "group_work": 5,
    "rounds": 2,
    "praise": 1,
    "warn": 1,
    "incident": 2,
}


class MockBackend:
    """API 키 없이 동작하는 결정적 규칙 기반 백엔드.

    감독 스키마 요청이면 게이지를 페르소나 속성의 함수로 갱신하고 발화자를 고르며,
    학생 발화 요청이면 성격·상태 기반 템플릿 대사를 만든다.
    """

    supports_cache = False

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(20260813 if seed is None else seed)

    # -- 공개 API --

    def complete_json(
        self,
        *,
        system: Any,
        messages: list[dict],
        schema: dict,
        max_tokens: int = 2048,
        model_role: str = "actor",
    ) -> dict:
        payload = extract_payload(messages)
        props = schema.get("properties", {})
        if "speakers" in props:
            return self._direct(payload)
        if "lines" in props:
            return self._group_talk(payload)
        if "utterance" in props:
            return self._speak(payload)
        return {}

    def complete_text(
        self,
        *,
        system: Any,
        messages: list[dict],
        max_tokens: int = 2048,
        model_role: str = "actor",
    ) -> str:
        payload = extract_payload(messages)
        task = payload.get("task")
        if task == "summary":
            text = re.sub(r"\s+", " ", payload.get("text", "")).strip()
            return (text[:400] + " …(이하 생략)") if len(text) > 400 else text
        if task == "analysis":
            return (
                "- **발문 수준**: (mock 백엔드 고정 응답) 사실확인형 발문이 많고 "
                "원리를 묻는 발문이 상대적으로 적습니다.\n"
                "- **개선 제안 1**: 정답을 확인하는 질문 뒤에 \"왜 그렇게 되지?\"를 한 번 더 붙여 "
                "원리형 발문으로 확장하세요.\n"
                "- **개선 제안 2**: 발언 기회가 없던 학생에게 짧은 확인 질문이나 짝 활동 발표를 배정하세요.\n"
                "- **개선 제안 3**: 설명이 10분을 넘기기 전에 활동이나 판서로 국면을 전환하세요.\n\n"
                "_(이 문단은 mock 백엔드의 고정 문구입니다. 실제 분석은 anthropic 백엔드에서 생성됩니다.)_"
            )
        return "(mock 백엔드 응답)"

    # -- 감독 --

    def _direct(self, p: dict) -> dict:
        action = p.get("action") or {}
        kind = action.get("kind", "teacher_say")
        text = action.get("text", "") or ""
        target = action.get("target")
        minute = int(p.get("minute", 0))
        phase = p.get("phase", "도입")

        minute_delta = _MINUTE_COST.get(kind, 1)
        if kind == "time_skip":
            minute_delta = max(1, int(action.get("minutes", 5)))
        new_minute = minute + minute_delta

        # 국면 전환 규칙
        if kind == "activity":
            phase = "활동"
        elif kind in ("group_form", "group_work"):
            phase = "모둠활동"
        elif phase == "도입" and new_minute >= 8:
            phase = "전개"
        if new_minute >= 35 and phase not in ("정리", "종료"):
            phase = "정리"

        refreshing = kind in ("activity", "group_work", "group_form", "rounds", "incident")

        updates: list[dict] = []
        detail: dict[str, dict] = {}
        for s in p.get("students", []):
            sid = s["id"]
            st = s.get("state", {})
            traits = " ".join(s.get("traits", []))
            short_attention = "짧" in traits

            focus = float(st.get("focus", 70))
            comp = float(st.get("comprehension", 60))
            interest = float(st.get("interest", 60))

            # 집중: 시간이 지날수록 감쇠, 주의집중이 짧은 학생은 더 빨리
            decay = minute_delta * (2.6 if short_attention else 1.3)
            if refreshing:
                decay -= 8                 # 활동·순회·돌발은 환기 효과
            decay = max(decay, -5.0)       # 환기로 회복되는 폭에는 상한이 있다
            if kind == "incident":
                decay += 5                 # 다만 돌발은 어수선함도 만든다
            decay += (minute / 40.0) * minute_delta * 0.8  # 수업 후반 누적 피로
            focus -= decay
            if sid == target:
                focus += 15

            # 이해도: 성취수준의 함수 + 집중의 영향
            drift = _LEVEL_DRIFT.get(s.get("achievement_level", "중"), 0.0) * (minute_delta * 0.6)
            if kind == "board":
                drift += 2.0
            if kind == "rounds" and sid == target:
                drift += 8.0
            if kind == "group_work":
                drift += 1.5
            comp += drift + (focus - 60) * 0.05

            # 흥미: 관심사 연결과 활동 유형
            interest -= minute_delta * 0.5
            if any(k and k in text for k in s.get("interests", [])):
                interest += 14
            if kind in ("activity", "group_work"):
                interest += 8
            if kind == "praise" and sid == target:
                interest += 6
            if kind == "warn" and sid == target:
                interest -= 6

            focus_i = _clamp(focus)
            comp_i = _clamp(comp)
            interest_i = _clamp(interest)

            # 정서
            anxious = any(t in traits for t in _ANXIOUS_TRAITS)
            if sid == target and kind in ("nominate", "warn") and anxious:
                emotion = "불안"
            elif sid == target and kind == "praise":
                emotion = "들뜸"
            elif sid == target and kind == "warn":
                emotion = "위축"
            elif comp_i < 40:
                emotion = "위축"
            elif focus_i < 35:
                emotion = "지루함"
            elif interest_i >= 75 and focus_i >= 65:
                emotion = "몰입"
            else:
                emotion = "평온"

            # 겉으로 보이는 모습
            if emotion == "불안":
                visible = "고개를 숙이고 손을 만지작거림"
            elif focus_i < 30:
                visible = self.rng.choice(_IDLE_ACTIONS)
            elif focus_i >= 75 and interest_i >= 70:
                visible = "몸을 앞으로 기울여 듣고 있음"
            elif comp_i < 40:
                visible = "공책을 멍하니 보고 있음"
            else:
                visible = ""

            updates.append({
                "id": sid,
                "comprehension": comp_i,
                "interest": interest_i,
                "focus": focus_i,
                "emotion": emotion,
                "visible_action": visible,
            })
            detail[sid] = {
                "name": s.get("name", sid),
                "traits": traits,
                "focus": focus_i,
                "comprehension": comp_i,
                "interest": interest_i,
                "emotion": emotion,
                "anxious": anxious,
            }

        speakers = self._pick_speakers(kind, target, detail)
        narration = self._narration(kind, detail, new_minute)

        return {
            "minute_delta": minute_delta,
            "phase": phase,
            "updates": updates,
            "speakers": speakers,
            "narration": narration,
        }

    def _pick_speakers(self, kind: str, target: str | None, detail: dict[str, dict]) -> list[dict]:
        speakers: list[dict] = []
        if target and target in detail:
            speakers.append({"id": target, "cue": self._cue(kind, detail[target], nominated=True)})

        if kind in ("group_form", "group_work"):
            extra = 0
        elif kind in ("nominate", "rounds", "praise", "warn"):
            extra = 1 if self.rng.random() < 0.35 else 0
        elif kind == "time_skip":
            extra = 1
        else:
            extra = self.rng.choice((1, 1, 2))

        if extra:
            pool = []
            for sid, d in detail.items():
                if any(sp["id"] == sid for sp in speakers):
                    continue
                score = d["focus"] + self.rng.uniform(0, 15)
                if any(t in d["traits"] for t in _ACTIVE_TRAITS):
                    score += 20
                if d["anxious"]:
                    score -= 20
                if d["comprehension"] < 40:
                    score += 5  # 모르겠다는 반응도 겉으로 드러나는 반응이다
                pool.append((score, sid))
            pool.sort(reverse=True)
            for _, sid in pool[:extra]:
                speakers.append({"id": sid, "cue": self._cue(kind, detail[sid], nominated=False)})

        return speakers[:3]

    @staticmethod
    def _cue(kind: str, d: dict, *, nominated: bool) -> str:
        if nominated and d["anxious"]:
            return "지목당해 긴장한 상태다. 아는 것도 잘 말하지 못한다."
        if d["comprehension"] < 40:
            return "지금 설명을 따라오지 못하고 있다. 모르는 티를 내라."
        if d["focus"] < 35:
            return "딴짓 중이었다. 방금 내용을 놓친 반응을 해라."
        if kind == "praise":
            return "칭찬을 받았다. 그 학생답게 반응해라."
        if kind == "warn":
            return "주의를 받았다. 그 학생답게 반응해라."
        if d["interest"] >= 75:
            return "지금 내용에 흥미를 느끼고 있다. 적극적으로 반응해라."
        return "지금 수업 내용에 그 학생답게 반응해라."

    @staticmethod
    def _narration(kind: str, detail: dict[str, dict], minute: int) -> str:
        base = {
            "board": "칠판에 쓴 내용을 옮겨 적는 소리가 이어진다.",
            "activity": "책상을 돌려 앉으며 교실이 잠시 어수선해진다.",
            "group_form": "모둠별로 자리를 옮기는 소리가 난다.",
            "group_work": "모둠마다 말소리가 겹쳐 교실이 웅성거린다.",
            "rounds": "선생님이 한 자리에 멈춰 서자 주변이 조금 조용해진다.",
            "time_skip": "활동 시간이 지나고 학생들이 자리로 돌아온다.",
            "incident": "예상치 못한 일이 생겨 시선이 한쪽으로 쏠린다.",
        }.get(kind, "교실은 대체로 조용하지만 여기저기 작은 움직임이 있다.")

        if not detail:
            return base
        worst = min(detail.values(), key=lambda d: d["focus"])
        if worst["focus"] < 40:
            base += f" {worst['name']}의 시선이 앞을 벗어나 있다."
        elif minute >= 30:
            base += " 수업 후반으로 갈수록 몸을 뒤척이는 학생이 늘어난다."
        return base

    # -- 학생 발화 --

    def _speak(self, p: dict) -> dict:
        traits = " ".join(p.get("traits", []))
        st = p.get("state", {})
        comp = int(st.get("comprehension", 60))
        focus = int(st.get("focus", 70))
        interest = int(st.get("interest", 60))
        emotion = st.get("emotion", "평온")
        anxious = any(t in traits for t in _ANXIOUS_TRAITS)
        active = any(t in traits for t in _ACTIVE_TRAITS)
        nominated = bool(p.get("nominated"))

        if anxious and (nominated or emotion in ("불안", "위축")):
            return self.rng.choice((
                {"utterance": "", "action": "……(고개를 숙인다)"},
                {"utterance": "…….", "action": "입을 열었다가 다시 다문다"},
                {"utterance": "잘…… 모르겠어요.", "action": "목소리가 거의 들리지 않는다"},
                {"utterance": "", "action": "공책만 내려다보며 아무 말도 하지 못한다"},
                {"utterance": "저…… 나중에 말해도 돼요?", "action": "손끝을 만지작거린다"},
            ))

        if comp < 40:
            return self.rng.choice((
                {"utterance": "어…… 그게 무슨 말이에요?", "action": ""},
                {"utterance": "잘 모르겠어요.", "action": "연필을 내려놓는다"},
                {"utterance": "어차피 저는 못 할 것 같은데요.", "action": ""},
                {"utterance": "선생님, 앞에 거부터 다시 알려주시면 안 돼요?", "action": ""},
                {"utterance": "", "action": "고개를 끄덕이지만 공책은 비어 있다"},
                {"utterance": "이거 그냥 빼기로 하면 안 돼요?", "action": ""},
            ))

        if focus < 35:
            return self.rng.choice((
                {"utterance": "네? 뭐라고 하셨어요?", "action": "창밖을 보다 고개를 든다"},
                {"utterance": "", "action": "옆 친구에게 방금 뭐라고 했냐고 묻는다"},
                {"utterance": "아, 그거…… 몇 쪽이에요?", "action": ""},
                {"utterance": "", "action": "지우개를 굴리다 선생님과 눈이 마주친다"},
                {"utterance": "다시 한 번만 말해 주세요.", "action": ""},
            ))

        if active or interest >= 75:
            return self.rng.choice((
                {"utterance": "선생님, 그럼 순서를 바꾸면 답도 달라져요?", "action": "손을 번쩍 든다"},
                {"utterance": "이거 아까 배운 거랑 비슷한 거 아니에요?", "action": ""},
                {"utterance": "저요! 제가 말해 볼게요.", "action": "몸을 앞으로 내민다"},
                {"utterance": "그럼 이런 경우에도 똑같이 되는 거예요?", "action": ""},
                {"utterance": "아, 알겠다! 그러니까 나눠서 비교하는 거네요.", "action": ""},
                {"utterance": "선생님, 왜 그렇게 되는 거예요?", "action": ""},
            ))

        return self.rng.choice((
            {"utterance": "아, 알 것 같아요.", "action": ""},
            {"utterance": "네, 알겠습니다.", "action": "공책에 받아 적는다"},
            {"utterance": "이렇게 쓰면 되는 거 맞죠?", "action": "공책을 들어 보인다"},
            {"utterance": "음…… 조금 헷갈리는데 한 번 더 해 볼게요.", "action": ""},
            {"utterance": "", "action": "고개를 끄덕이며 필기를 이어간다"},
            {"utterance": "친구랑 같이 해 봐도 돼요?", "action": ""},
        ))

    # -- 모둠 대화 1라운드 --

    def _group_talk(self, p: dict) -> dict:
        members = p.get("group", [])
        if not members:
            return {"lines": []}
        count = min(len(members), self.rng.choice((2, 3)))
        # 집중이 높은 순으로 후보를 만들되 약간의 흔들림을 준다
        ranked = sorted(
            members,
            key=lambda m: -(m.get("state", {}).get("focus", 60) + self.rng.uniform(0, 20)),
        )
        lines = []
        for i, m in enumerate(ranked[:count]):
            spoken = self._speak({
                "traits": m.get("traits", []),
                "state": m.get("state", {}),
                "nominated": False,
            })
            if i == 0 and not spoken["utterance"]:
                spoken = {"utterance": "우리 이거 누가 먼저 할래?", "action": ""}
            lines.append({
                "id": m["id"],
                "utterance": spoken["utterance"],
                "action": spoken["action"],
            })
        return {"lines": lines}


def _clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


# --------------------------------------------------------------------------
# 팩토리
# --------------------------------------------------------------------------

def make_backend(
    name: str,
    *,
    seed: int | None = None,
    director_model: str = DEFAULT_DIRECTOR_MODEL,
    actor_model: str = DEFAULT_ACTOR_MODEL,
) -> LLMBackend:
    """백엔드 생성. name은 "anthropic" 또는 "mock"."""
    key = (name or "").strip().lower()
    if key == "anthropic":
        return AnthropicBackend(director_model=director_model, actor_model=actor_model)
    if key == "mock":
        return MockBackend(seed=seed)
    raise ValueError(f"알 수 없는 백엔드: {name!r} (anthropic|mock)")
