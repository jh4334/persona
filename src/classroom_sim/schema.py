"""속성 카탈로그(personas/schema/dimensions.json) 조회 및 문서 생성 도구.

사용 예:
    PYTHONPATH=src python -m classroom_sim.schema            # 그룹별 속성 목록 출력
    PYTHONPATH=src python -m classroom_sim.schema --render docs/dimension_reference.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_CATALOG = (
    Path(__file__).resolve().parents[2] / "personas" / "schema" / "dimensions.json"
)


def load_catalog(path: str | Path = DEFAULT_CATALOG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_markdown(catalog: dict) -> str:
    total = sum(len(g["dimensions"]) for g in catalog["groups"])
    lines = [
        "# 속성 카탈로그 레퍼런스",
        "",
        f"_이 문서는 `personas/schema/dimensions.json` (v{catalog['version']})에서 자동 생성되었습니다. "
        f"직접 수정하지 말고 카탈로그를 수정한 뒤 다시 생성하세요._",
        "",
        f"총 **{len(catalog['groups'])}개 그룹, {total}개 속성**. "
        "'권장 값'은 예시 척도이며 자유 서술도 허용됩니다.",
        "",
    ]
    for g in catalog["groups"]:
        lines.append(f"## {g['label']} (`{g['key']}`, {len(g['dimensions'])}개)")
        lines.append("")
        lines.append(g["description"])
        lines.append("")
        lines.append("| 속성 키 | 설명 | 권장 값 |")
        lines.append("|---|---|---|")
        for d in g["dimensions"]:
            values = " / ".join(d["values"]) if d["values"] else "_(자유 서술)_"
            lines.append(f"| `{d['key']}` | {d['description']} | {values} |")
        lines.append("")
    return "\n".join(lines)


def print_summary(catalog: dict) -> None:
    total = sum(len(g["dimensions"]) for g in catalog["groups"])
    print(f"속성 카탈로그 v{catalog['version']} — {len(catalog['groups'])}개 그룹, {total}개 속성\n")
    for g in catalog["groups"]:
        keys = ", ".join(d["key"] for d in g["dimensions"])
        print(f"[{g['label']}] ({g['key']}, {len(g['dimensions'])}개)")
        print(f"  {keys}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="속성 카탈로그 조회/문서 생성")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="카탈로그 JSON 경로")
    parser.add_argument("--render", metavar="OUT_MD", help="마크다운 레퍼런스 문서를 생성할 경로")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    if args.render:
        out = Path(args.render)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(catalog), encoding="utf-8")
        print(f"생성 완료: {out}")
    else:
        print_summary(catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
