"""학급/학생 페르소나 로딩 및 검증.

스키마 v2: 기본 필드 + 5개 속성 그룹(cognitive, language, motivation,
behavior_social, environment). 속성 그룹은 모두 선택이며, 자세한 작성법은
docs/persona_schema.md 참조. v1 파일(속성 그룹 없음)도 그대로 동작한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 프롬프트에 표시할 속성 그룹 이름 (표시 순서 유지)
# 전체 속성 카탈로그(그룹별 세부 속성 100개)는 personas/schema/dimensions.json 참조
ATTRIBUTE_GROUPS: dict[str, str] = {
    "cognitive": "인지·학습 능력",
    "subject_skills": "교과 역량",
    "language": "언어 능력",
    "motivation": "동기·정서",
    "behavior_social": "행동·사회성",
    "study_habits": "학습 습관·자기관리",
    "environment": "배경·환경",
    "health_development": "건강·발달 배려",
    "digital": "디지털·매체",
}


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
    # 속성 그룹 — {"문해력": "학년 수준", ...} 형태의 키-값 (권장 키: dimensions.json)
    cognitive: dict[str, str] = field(default_factory=dict)
    subject_skills: dict[str, str] = field(default_factory=dict)
    language: dict[str, str] = field(default_factory=dict)
    motivation: dict[str, str] = field(default_factory=dict)
    behavior_social: dict[str, str] = field(default_factory=dict)
    study_habits: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    health_development: dict[str, str] = field(default_factory=dict)
    digital: dict[str, str] = field(default_factory=dict)

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
        for key, label in ATTRIBUTE_GROUPS.items():
            attrs: dict[str, str] = getattr(self, key)
            if attrs:
                lines.append(f"[{label}]")
                lines.extend(f"  - {k}: {v}" for k, v in attrs.items())
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
    students = []
    for s in data["students"]:
        students.append(
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
                **{g: dict(s.get(g, {})) for g in ATTRIBUTE_GROUPS},
            )
        )
    if not students:
        raise ValueError(f"{path}: students 목록이 비어 있습니다.")
    return Classroom(
        class_name=data.get("class_name", "이름 없는 학급"),
        grade=data.get("grade", ""),
        description=data.get("description", ""),
        students=students,
    )
