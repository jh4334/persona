# 학생 페르소나 스키마 v2.1

MatrAIx의 페르소나 속성 체계(배경/심리/능력/행동 4영역, 1,290개 차원)를 참고해 만든 교실용 스키마입니다. MatrAIx의 세부 속성은 소비자 조사용(인구통계, 가치관, 소비 습관 등)이므로, **세부 속성은 교실 상황에 맞게 새로 설계**했습니다.

## 구성 요소

| 파일 | 역할 |
|---|---|
| `personas/schema/dimensions.json` | **속성 카탈로그 원본** — 9개 그룹, 102개 속성의 정의·권장 척도 (기계 판독용) |
| [`docs/dimension_reference.md`](dimension_reference.md) | 카탈로그에서 자동 생성된 사람용 레퍼런스 표 |
| `personas/class_6_3.json` | 카탈로그를 적용한 샘플 학급 (12명) |

카탈로그 조회·문서 재생성:

```bash
PYTHONPATH=src python -m classroom_sim.schema                                   # 그룹·속성 목록 출력
PYTHONPATH=src python -m classroom_sim.schema --render docs/dimension_reference.md  # 레퍼런스 재생성
```

## 그룹 구조

MatrAIx 4영역을 교실용 9그룹으로 확장했습니다.

```
MatrAIx 4영역     →  교실용 9그룹 (102개 속성)
──────────────────────────────────────────────
능력 (capability) →  cognitive          인지·학습 능력 (18)
                     subject_skills     교과 역량 (14)
                     language           언어 능력 (8)
심리 (psychology) →  motivation         동기·정서 (14)
행동 (behavior)   →  behavior_social    행동·사회성 (14)
                     study_habits       학습 습관·자기관리 (10)
배경 (background) →  environment        배경·환경 (10)
                     health_development 건강·발달 배려 (8)
                     digital            디지털·매체 (6)
```

## 학생 JSON 구조

```jsonc
{
  "id": "S01",                       // ── 기본 필드 (필수)
  "name": "김하늘",
  "achievement_level": "상",
  "prior_knowledge": "...",
  "learning_style": "...",
  "interests": ["코딩"],
  "personality": "...",
  "social": "...",
  "notes": "...",                    // 교사 메모 (선택)

  "cognitive": {                     // ── 속성 그룹 (모두 선택)
    "주의집중_지속시간": "5~15분",     //    키: dimension_reference.md의 속성 키
    "작업기억": "두 단계까지 가능"      //    값: 권장 척도 또는 자유 서술
  },
  "subject_skills": { "수학_연산": "학년 수준 이상" },
  "language": { ... },
  "motivation": { ... },
  "behavior_social": { ... },
  "study_habits": { ... },
  "environment": { ... },
  "health_development": { ... },
  "digital": { ... }
}
```

- 그룹과 속성은 **전부 선택**입니다. 비어 있으면 프롬프트에서 생략됩니다. 다만 시뮬레이션 품질은 채워진 정보량에 비례합니다.
- 값은 권장 척도 그대로 써도 되고, `"5~15분 — 오후 수업에는 더 짧아짐"`처럼 자유롭게 덧붙여도 됩니다.
- 카탈로그에 없는 키를 써도 동작하지만, 학급 간 비교·통계를 위해 카탈로그 키 사용을 권장합니다.

## 작성 원칙

1. **가상 페르소나만 사용하세요.** 실제 학생의 실명·진단명·가정사를 그대로 넣지 마세요. 실제 학급을 반영하고 싶다면 "우리 반에 이런 유형의 학생이 있다" 수준으로 익명화·일반화하세요.
2. **진단명 대신 '필요한 배려'를 쓰세요.** 특히 `health_development` 그룹은 진단명(예: ADHD)이 아니라 교실에서 관찰되는 행동과 필요한 배려(예: "15분 넘는 설명은 뒷부분을 놓침 — 활동 전환이 잦은 수업이 잘 맞음")로 기록합니다.
3. **결손과 강점을 함께 쓰세요.** "수리력 낮음"만 있는 학생보다 "수리력 낮음 + 구체물 조작에 강함"인 학생이 더 현실적인 예측과 쓸모 있는 지도 전략을 만들어냅니다.
4. **값은 관찰 가능한 행동으로 쓰세요.** `"머리가 나쁨"`(낙인) 대신 `"여러 단계 지시를 한 번에 기억하기 어려움"`(관찰된 행동)처럼 쓰면 예측도 지도 전략도 구체적으로 나옵니다.
5. **다 채우려 하지 마세요.** 102개는 어휘 사전이지 체크리스트가 아닙니다. 학생당 15~30개, 시뮬레이션할 단원과 관련 있는 속성 위주로 채우는 것이 효율적입니다.
