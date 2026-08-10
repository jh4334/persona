"""학급/학생 페르소나 로딩 및 검증."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Student:
    id: str
    name: str
    achievement_level: str
    prior_knowledge: str = ""
    learning_style: str = ""
    interests: list[str] = field(default_factory=list)
    personality: str = ""
    social: str = ""
    notes: str = ""

    def to_prompt_block(self) -> str:
        """시뮬레이션 프롬프트에 넣을 학생 프로필 텍스트."""
        lines = [
            f"학생 ID: {self.id}",
            f"이름: {self.name}",
            f"학업 성취 수준: {self.achievement_level}",
            f"사전 지식: {self.prior_knowledge}",
            f"학습 스타일: {self.learning_style}",
            f"흥미/관심사: {', '.join(self.interests) if self.interests else '정보 없음'}",
            f"성격: {self.personality}",
            f"교우 관계: {self.social}",
        ]
        if self.notes:
            lines.append(f"교사 메모: {self.notes}")
        return "\n".join(lines)


@dataclass
class Classroom:
    class_name: str
    grade: str
    description: str
    students: list[Student]


def load_classroom(path: str | Path) -> Classroom:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    students = [
        Student(
            id=s["id"],
            name=s["name"],
            achievement_level=s.get("achievement_level", "정보 없음"),
            prior_knowledge=s.get("prior_knowledge", ""),
            learning_style=s.get("learning_style", ""),
            interests=s.get("interests", []),
            personality=s.get("personality", ""),
            social=s.get("social", ""),
            notes=s.get("notes", ""),
        )
        for s in data["students"]
    ]
    if not students:
        raise ValueError(f"{path}: students 목록이 비어 있습니다.")
    return Classroom(
        class_name=data.get("class_name", "이름 없는 학급"),
        grade=data.get("grade", ""),
        description=data.get("description", ""),
        students=students,
    )
