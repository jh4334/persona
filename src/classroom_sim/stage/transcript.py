"""수업 전사(transcript) — 하나의 사실, 여러 관점.

무대에서 일어난 모든 일을 시간순으로 기록하고, 학생별 "그 학생이 실제로
보고 들었을 부분"만 뽑아내는 관점 필터를 제공한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 집중도가 이 값 미만이던 구간의 교사 발화는 학생 관점에서 들리지 않은 것으로 처리한다.
FOCUS_MISS_THRESHOLD = 40
MISSED_TEXT = "(…딴생각을 하느라 잘 못 들었다)"


@dataclass
class TranscriptEntry:
    turn: int
    minute: int
    actor: str                              # "교사" | 학생 id | "무대"
    kind: str                               # teacher_say|teacher_action|student_say|...
    content: str
    focus_map: dict[str, int] = field(default_factory=dict)  # 그 시점 학생별 집중값
    meta: dict = field(default_factory=dict)                 # 지목 대상 등 부가 정보

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "minute": self.minute,
            "actor": self.actor,
            "kind": self.kind,
            "content": self.content,
            "focus_map": dict(self.focus_map),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TranscriptEntry":
        return cls(
            turn=int(d.get("turn", 0)),
            minute=int(d.get("minute", 0)),
            actor=d.get("actor", "무대"),
            kind=d.get("kind", "system"),
            content=d.get("content", ""),
            focus_map={k: int(v) for k, v in (d.get("focus_map") or {}).items()},
            meta=dict(d.get("meta") or {}),
        )


class Transcript:
    """시간순 전사 기록."""

    def __init__(self, names: dict[str, str] | None = None) -> None:
        self.entries: list[TranscriptEntry] = []
        # 학생 id → 이름 (관점 텍스트 표시용). 없으면 id를 그대로 쓴다.
        self.names: dict[str, str] = dict(names or {})

    # ---------- 기록 ----------

    def add(
        self,
        *,
        turn: int,
        minute: int,
        actor: str,
        kind: str,
        content: str,
        focus_map: dict[str, int] | None = None,
        meta: dict | None = None,
    ) -> TranscriptEntry:
        entry = TranscriptEntry(
            turn=turn,
            minute=minute,
            actor=actor,
            kind=kind,
            content=content,
            focus_map=dict(focus_map or {}),
            meta=dict(meta or {}),
        )
        self.entries.append(entry)
        return entry

    def recent(self, count: int = 12) -> list[TranscriptEntry]:
        return self.entries[-count:] if count > 0 else list(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    # ---------- 표시 ----------

    def _label(self, actor: str) -> str:
        if actor == "교사":
            return "선생님"
        if actor == "무대":
            return "무대"
        return self.names.get(actor, actor)

    def render(self, entries: list[TranscriptEntry] | None = None) -> str:
        """객관적 전사 텍스트 (감독·리포트용)."""
        rows = self.entries if entries is None else entries
        lines: list[str] = []
        for e in rows:
            label = self._label(e.actor)
            if e.kind in ("teacher_say", "student_say"):
                lines.append(f"[{e.minute}분] {label}: \"{e.content}\"")
            elif e.kind in ("teacher_action", "student_action"):
                lines.append(f"[{e.minute}분] {label}: ({e.content})")
            elif e.kind == "narration":
                lines.append(f"[{e.minute}분] (무대) {e.content}")
            else:
                lines.append(f"[{e.minute}분] * {e.content}")
        return "\n".join(lines)

    def perspective_for(self, student_id: str, max_events: int = 40) -> str:
        """그 학생 관점의 전사 텍스트.

        집중이 40 미만이던 구간의 교사 발화는 "(…딴생각을 하느라 잘 못 들었다)"로
        대체한다. 본인의 발화·행동은 항상 그대로 보인다.
        """
        rows = self.entries[-max_events:] if max_events > 0 else list(self.entries)
        lines: list[str] = []
        for e in rows:
            focus = e.focus_map.get(student_id, 100)
            label = self._label(e.actor)
            if e.kind == "teacher_say":
                if focus < FOCUS_MISS_THRESHOLD:
                    lines.append(f"선생님: {MISSED_TEXT}")
                else:
                    lines.append(f"선생님: \"{e.content}\"")
            elif e.kind == "teacher_action":
                lines.append(f"선생님: ({e.content})")
            elif e.kind == "student_say":
                who = "나" if e.actor == student_id else label
                lines.append(f"{who}: \"{e.content}\"")
            elif e.kind == "student_action":
                who = "나" if e.actor == student_id else label
                lines.append(f"{who}: ({e.content})")
            elif e.kind == "narration":
                lines.append(f"(교실) {e.content}")
            else:
                lines.append(f"* {e.content}")
        return "\n".join(lines)

    # ---------- 접기(요약) ----------

    def fold(self, upto: int, summary: str) -> None:
        """앞부분 entries[:upto]를 요약 한 줄로 접는다(비용 억제)."""
        if upto <= 0 or upto > len(self.entries):
            return
        head = self.entries[:upto]
        folded = TranscriptEntry(
            turn=head[0].turn,
            minute=head[0].minute,
            actor="무대",
            kind="system",
            content=f"[앞부분 요약] {summary}",
            focus_map={},
            meta={"folded": len(head)},
        )
        self.entries = [folded] + self.entries[upto:]

    # ---------- 직렬화 ----------

    def to_json(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"names": self.names, "entries": self.to_json()}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Transcript":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):  # entries만 저장된 형태도 허용
            names, rows = {}, data
        else:
            names, rows = data.get("names", {}), data.get("entries", [])
        t = cls(names=names)
        t.entries = [TranscriptEntry.from_dict(d) for d in rows]
        return t
