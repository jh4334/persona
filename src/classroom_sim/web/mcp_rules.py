"""ChatGPT가 연기한 결과를 심판하는 규칙.

`docs/specs/v0.6_chatgpt_app.md`의 핵심 설계를 구현한다. ChatGPT 앱 모드에서는
**모델이 무대 감독과 배우를 모두 맡고**, 우리 서버는 LLM을 전혀 호출하지 않는다
(그래서 운영비가 0이다). 대신 서버가 심판을 본다.

심판이 없으면 커스텀 GPT와 다를 게 없다. 긴 수업에서 모델은 자기가 정한 설정을
잊고, 이해도 30이던 학생을 근거 없이 90으로 만들며, 말 잘하는 학생에게만 계속
발언 기회를 준다. 그래서 매 턴 다음을 검사해 교정 지시를 돌려준다.

    · 게이지가 한 턴에 얼마나 움직일 수 있는가 (급변 차단)
    · 페르소나와 어긋나는 방향인가 (주의집중 짧은 학생이 30분째 몰입 등)
    · 발언 기회가 한쪽으로 쏠리지 않았는가
    · 시간·국면이 앞뒤가 맞는가

교정은 값을 강제로 자르는 것(hard)과 말로 짚어 주는 것(soft)으로 나뉜다.
값이 범위를 벗어난 것은 자르고, 개연성 문제는 다음 턴 지침으로 돌려준다.
"""

from __future__ import annotations

from ..stage.state import PHASES, clamp

MAX_GAUGE_STEP = 25       # 한 턴에 게이지가 움직일 수 있는 최대 폭
MAX_MINUTE_STEP = 15      # 한 턴에 흐를 수 있는 최대 분 (활동/시간 건너뛰기 제외)
MAX_MINUTE_SKIP = 40      # 시간 건너뛰기로도 이 이상은 한 번에 못 넘긴다
EQUITY_WINDOW = 12        # 발언 형평성을 볼 최근 턴 수
EQUITY_RATIO = 0.4        # 한 학생이 최근 발언의 이 비율을 넘으면 지적


def _num(v, fallback: int) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return fallback


def judge_gauges(prev: dict, claimed: dict) -> tuple[dict, list[str]]:
    """모델이 주장한 게이지를 검사해 (교정된 값, 지적 목록)을 돌려준다.

    prev/claimed 는 {student_id: {comprehension, interest, focus, emotion, visible_action}}.
    claimed 에 없는 학생은 이전 값을 유지한다 — 모델이 일부만 갱신해도 된다.
    """
    fixed: dict[str, dict] = {}
    notes: list[str] = []
    for sid, before in prev.items():
        after = dict(before)
        want = claimed.get(sid) or {}
        for key in ("comprehension", "interest", "focus"):
            base = _num(before.get(key), 60)
            new = clamp(_num(want.get(key, base), base))
            if abs(new - base) > MAX_GAUGE_STEP:
                capped = base + (MAX_GAUGE_STEP if new > base else -MAX_GAUGE_STEP)
                notes.append(
                    f"{sid}의 {key}를 {base}→{new}로 바꾸려 했습니다. 한 턴에 "
                    f"{MAX_GAUGE_STEP}점 넘게 움직이지 않습니다 — {capped}으로 조정했습니다. "
                    "큰 변화는 여러 턴에 걸쳐 일어나게 해 주세요.")
                new = capped
            after[key] = new
        if isinstance(want.get("emotion"), str) and want["emotion"].strip():
            after["emotion"] = want["emotion"].strip()[:20]
        if isinstance(want.get("visible_action"), str):
            after["visible_action"] = want["visible_action"].strip()[:120]
        fixed[sid] = after
    unknown = [s for s in claimed if s not in prev]
    if unknown:
        notes.append(f"이 학급에 없는 학생을 갱신하려 했습니다: {', '.join(unknown[:5])} — 무시했습니다.")
    return fixed, notes


def judge_persona(personas: dict, prev: dict, fixed: dict, minute: int) -> list[str]:
    """페르소나와 어긋나는 변화를 짚는다. 값을 강제하지는 않는다.

    규칙 자체를 도구 응답으로 돌려주는 것이 핵심이다 — 모델이 다음 턴에
    스스로 반영하게 만든다.
    """
    notes: list[str] = []
    for sid, after in fixed.items():
        p = personas.get(sid) or {}
        attrs = p.get("cognitive") or {}
        span = str(attrs.get("주의집중_지속시간") or "")
        # "5분 미만" / "5~15분" 처럼 적힌 상한을 대충 읽는다
        limit = None
        if "5분 미만" in span:
            limit = 5
        elif "5~15" in span:
            limit = 15
        elif "15~30" in span:
            limit = 30
        if limit and minute > limit + 10 and after.get("focus", 0) >= 75:
            notes.append(
                f"{sid}({p.get('name', sid)})는 주의집중 지속시간이 '{span}'인데 "
                f"{minute}분째 집중 {after['focus']}입니다. 이 시점이면 흐트러지는 것이 "
                "자연스럽습니다 — 활동 전환이나 개별 개입이 없었다면 낮춰 주세요.")
        before = prev.get(sid) or {}
        if (after.get("comprehension", 0) - _num(before.get("comprehension"), 60) >= 15
                and str(p.get("achievement_level", "")) in ("하", "중하")):
            notes.append(
                f"{sid}({p.get('name', sid)})는 성취 수준이 '{p.get('achievement_level')}'입니다. "
                "이해도가 한 번에 크게 오르려면 개별 지도나 성공 경험 같은 근거가 필요합니다.")
    return notes


def judge_equity(speak_log: list[list[str]], roster: list[str]) -> list[str]:
    """최근 발언 분포를 보고 쏠림·소외를 알린다."""
    notes: list[str] = []
    recent = speak_log[-EQUITY_WINDOW:]
    flat = [sid for turn in recent for sid in turn]
    if len(flat) < 6:
        return notes
    counts: dict[str, int] = {}
    for sid in flat:
        counts[sid] = counts.get(sid, 0) + 1
    top, n = max(counts.items(), key=lambda kv: kv[1])
    if n / len(flat) > EQUITY_RATIO:
        notes.append(
            f"최근 {len(recent)}턴 발언의 {n}/{len(flat)}이 {top}에게 쏠렸습니다. "
            "다른 학생에게도 기회를 주세요.")
    silent = [s for s in roster if s not in counts]
    if silent and len(recent) >= 6:
        notes.append(
            f"최근 {len(recent)}턴 동안 한 번도 드러나지 않은 학생: "
            f"{', '.join(silent[:6])}{' 외' if len(silent) > 6 else ''}. "
            "조용한 학생의 속마음이나 작은 행동도 장면에 넣어 주세요.")
    return notes


def judge_time(prev_minute: int, claimed_minute, kind: str) -> tuple[int, list[str]]:
    """경과 시간이 앞뒤가 맞는지 본다."""
    notes: list[str] = []
    want = _num(claimed_minute, prev_minute)
    if want < prev_minute:
        notes.append(f"수업 시간이 {prev_minute}분에서 {want}분으로 되돌아갔습니다 — 유지했습니다.")
        return prev_minute, notes
    cap = MAX_MINUTE_SKIP if kind == "time_skip" else MAX_MINUTE_STEP
    if want - prev_minute > cap:
        notes.append(
            f"한 턴에 {want - prev_minute}분이 흘렀습니다. "
            f"{cap}분을 넘기지 않습니다 — {prev_minute + cap}분으로 조정했습니다.")
        return prev_minute + cap, notes
    return want, notes


def judge_phase(prev_phase: str, claimed) -> tuple[str, list[str]]:
    if not isinstance(claimed, str) or not claimed.strip():
        return prev_phase, []
    p = claimed.strip()
    if p not in PHASES:
        return prev_phase, [f"'{p}'는 쓰지 않는 국면입니다 (가능: {', '.join(PHASES)}) — {prev_phase} 유지."]
    return p, []
