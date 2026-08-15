"""돌발 상황 카드 — 수업 중 무작위/선택 이벤트 주입."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Incident:
    name: str
    description: str


CARDS: tuple[Incident, ...] = (
    Incident(
        "친구갈등",
        "모둠 안에서 역할 분담을 두고 다툼이 벌어진다. 한 학생이 \"쟤가 아무것도 안 해요\"라고 큰 소리로 말하고, "
        "지목당한 학생은 얼굴이 붉어진 채 입을 다문다. 주변 학생들의 시선이 몰린다.",
    ),
    Incident(
        "기기고장",
        "교실 앞 TV(또는 태블릿)가 갑자기 꺼진다. 화면에 띄워 둔 자료가 사라지고, 다시 켜는 동안 "
        "학생들의 집중이 흐트러진다. 기기에 익숙한 학생 몇 명이 나서서 참견한다.",
    ),
    Incident(
        "방송소음",
        "복도 스피커에서 갑자기 교내 방송이 흘러나온다. 1~2분간 교사의 목소리가 묻히고, "
        "듣기에 의존하던 학생들이 설명의 앞뒤를 놓친다.",
    ),
    Incident(
        "조퇴요청",
        "한 학생이 배가 아프다며 보건실에 가고 싶다고 손을 든다. 실제로 아픈지 회피인지 분명하지 않다. "
        "교실 분위기가 잠깐 술렁인다.",
    ),
    Incident(
        "벌레소동",
        "창문으로 들어온 벌레 한 마리가 교실을 돌아다닌다. 몇 명이 소리를 지르며 자리에서 일어나고, "
        "다시 앉히는 데 시간이 걸린다.",
    ),
    Incident(
        "복도소란",
        "옆 반이 이동수업을 시작해 복도가 시끄러워진다. 학생들의 시선이 자꾸 문 쪽으로 향하고, "
        "주의집중이 짧은 학생부터 몸을 돌린다.",
    ),
)

_BY_NAME = {c.name: c for c in CARDS}


def names() -> list[str]:
    return [c.name for c in CARDS]


def draw(
    name: str | None = None,
    rng: random.Random | None = None,
    exclude: list[str] | None = None,
) -> Incident:
    """카드 뽑기. name이 없으면 무작위, 이름이 틀리면 부분 일치를 시도한다.

    exclude에 이미 나온 카드 이름을 넘기면 무작위 뽑기에서 제외한다
    (전부 나왔으면 다시 전체에서 뽑는다). 이름을 지정한 선택은 제외와 무관.
    """
    if name:
        key = name.strip()
        if key in _BY_NAME:
            return _BY_NAME[key]
        for card in CARDS:
            if key in card.name or card.name in key:
                return card
        raise KeyError(f"알 수 없는 돌발 카드: {name} (사용 가능: {', '.join(names())})")
    picker = rng or random
    pool = [c for c in CARDS if c.name not in (exclude or [])] or list(CARDS)
    return picker.choice(pool)
