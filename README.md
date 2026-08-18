# 교실 페르소나 시뮬레이터 (Classroom Persona Simulator)

[MatrAIx](https://github.com/MatrAIx-ai/MatrAIx-Persona-8B)의 페르소나 기반 시뮬레이션 아이디어를 **교실 상황**에 적용한 프로토타입입니다.

학생별 페르소나(성취 수준, 사전 지식, 학습 스타일, 성격, 흥미 등)를 정의해 두면, 특정 **학습단원(수업 계획)** 에 대해 각 학생이 어떻게 반응할지 Claude API로 시뮬레이션하고 교사용 리포트를 생성합니다.

```
학생 페르소나 (JSON)  ×  학습단원 (Markdown)
        │
        ▼
  학생별 반응 시뮬레이션 (Claude API, 병렬 실행)
        │
        ▼
  교사용 리포트 (Markdown)
  ├─ 학생별 예상 이해도 / 흥미도 (1~5)
  ├─ 예상 반응 · 질문 · 오개념 · 난점
  ├─ 학생별 맞춤 지도 전략
  └─ 학급 종합 분석 및 수업 조정 제안
```

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. API 키 설정 (https://platform.claude.com 에서 발급)
export ANTHROPIC_API_KEY=sk-ant-...

# 3. 샘플 학급(12명) × 샘플 단원(비와 비율)으로 실행
PYTHONPATH=src python -m classroom_sim \
    --personas personas/class_6_3.json \
    --lesson lessons/ratio_and_rate.md \
    --out reports/
```

실행이 끝나면 `reports/ratio_and_rate_report.md`가 생성됩니다. 출력 예시는 [docs/example_report.md](docs/example_report.md)를 참고하세요.

## 교실 무대 — 실시간 수업 시뮬레이션 (v0.3~v0.5)

일괄 리포트 대신, 교사가 한 마디씩 수업을 진행하며 학생들이 실시간으로 반응하는 모드입니다.

```bash
# 터미널판 — API 키 없이 mock 백엔드로 바로 체험 가능
PYTHONPATH=src python -m classroom_sim.stage \
    --personas personas/class_6_3.json --lesson lessons/ratio_and_rate.md \
    --backend mock          # API 키 없이 바로 체험 (규칙 기반)
#   --backend codex         # ChatGPT 구독으로 실제 AI 반응 (npm i -g @openai/codex 후 codex login, API 과금 없음)
#   --backend anthropic     # Claude API 사용 (ANTHROPIC_API_KEY 또는 ant auth login)

# 웹판 — 게더타운풍 도트 교실 (브라우저에서 http://localhost:8000)
pip install -r requirements.txt
PYTHONPATH=src python -m classroom_sim.web --port 8000

# 📱 휴대폰에서 접속하려면: PC와 휴대폰을 같은 Wi-Fi에 두고
PYTHONPATH=src python -m classroom_sim.web --port 8000 --host 0.0.0.0
# 기동 시 출력되는 http://<PC의 IP>:8000 주소를 휴대폰 브라우저에서 열기
# (화면이 자동으로 모바일 레이아웃으로 전환됩니다)
```

수업 중 명령: 일반 텍스트(전체 발화), `@이름 질문`(지목, 자동완성 지원), `/판서`, `/활동`, `/모둠 4인`, `/모둠활동`, `/순회 이름`, `/칭찬`, `/주의`, `/시간 10분`, `/돌발`, `/상태`, `/도움말`, `/종료`(사후 리포트 + 수업 분석 생성, `reports/stage/`에 자동 저장). 도트 교실의 픽셀아트 에셋 제작 가이드는 [docs/asset_request.md](docs/asset_request.md)를 참고하세요 (에셋이 없어도 임시 스프라이트로 동작).

새로고침·서버 재시작 후에도 진행 중 수업을 "이어하기"로 재개할 수 있고(세션 스냅샷), 상태 확인은 `GET /healthz`, 회귀 테스트는 `python tests/regression/run_all.py`로 실행합니다. 공개 인터넷에 올리거나 여러 교사가 나눠 쓴다면 **로그인(Supabase Auth 이메일 인증)** 과 세션 스냅샷의 클라우드 저장을 켤 수 있습니다 — [docs/supabase_setup.md](docs/supabase_setup.md) 참조. 설정하지 않으면 기존대로 로그인 없이 로컬 디스크만 사용합니다(같은 Wi-Fi 안에서 쓰는 전제). 출시 준비 상태·남은 리스크·체크리스트는 **[docs/release_checklist.md](docs/release_checklist.md)** 를 참고하세요.

### CLI 옵션

| 옵션 | 설명 |
|---|---|
| `--personas` | 학급 페르소나 JSON 파일 (필수) |
| `--lesson` | 학습단원 Markdown 파일 (필수) |
| `--out` | 리포트 출력 디렉터리 (기본 `reports/`) |
| `--workers` | 동시 API 요청 수 (기본 4) |
| `--no-synthesis` | 학급 종합 분석 생략 (API 호출 1회 절약) |

## 나만의 학급 만들기

웹판에서는 셋업 화면의 **[+ 내 학급 만들기]** 로 JSON 없이 폼으로 학급을 만들 수 있습니다 — 성취 수준별 인원을 한 번에 만들고, 학생을 복제하고, 102개 속성 중 필요한 것만 골라 채웁니다(전부 선택 사항). 이미 학급 파일이 있다면 JSON 탭에 붙여넣어도 됩니다. 만든 학급은 만든 사람에게만 보입니다. 파일로 관리하려면 `personas/class_6_3.json`을 복사해 수정하세요. MatrAIx의 4영역 속성 체계(배경/심리/능력/행동)를 교실용으로 재설계한 **9개 그룹 · 102개 속성 카탈로그**(`personas/schema/dimensions.json`)에서 필요한 속성을 골라 학생별로 채웁니다. 전체 속성 목록은 [docs/dimension_reference.md](docs/dimension_reference.md), 작성 원칙은 [docs/persona_schema.md](docs/persona_schema.md)를 참고하세요. 기본 필드:

```jsonc
{
  "id": "S01",
  "name": "김하늘",
  "achievement_level": "상",          // 상 / 중상 / 중 / 하 등 자유 표기
  "prior_knowledge": "선행학습으로 ...",
  "learning_style": "시각 자료를 선호 ...",
  "interests": ["코딩", "수학 퍼즐"],
  "personality": "자신감이 높고 ...",
  "social": "친구들에게 잘 알려주는 편",
  "notes": "심화 과제가 없으면 지루해함"   // 교사 메모 (선택)
}
```

학습단원은 자유 형식의 Markdown이면 됩니다. 학습 목표, 주요 개념, 수업 흐름이 들어 있을수록 예측이 구체적으로 나옵니다.

## 구현 노트

- **모델**: `claude-opus-5` (안전 분류기 거부 시 자동 대체 모델로 재시도하는 server-side fallback 사용)
- **Structured Outputs**: 학생별 결과를 JSON 스키마로 강제해 파싱 오류 없이 수집
- **Prompt Caching**: 수업 자료를 system 프롬프트에 캐싱해 학생 수가 많아도 입력 비용 절감 (첫 요청으로 캐시를 만든 뒤 나머지를 병렬 실행)
- **비용 감각**: 학생 12명 + 종합 분석 기준 요청 13회. 수업 자료 분량에 따라 다르지만 대략 수백 원~수천 원 수준

## 한계와 주의사항

- **시뮬레이션은 예측일 뿐입니다.** 실제 학생의 반응을 보장하지 않으며, 수업 설계의 참고 자료로만 사용하세요. (MatrAIx 논문에서도 페르소나 일관성은 91.5%로, 완벽하지 않습니다.)
- **실제 학생의 개인정보를 입력하지 마세요.** 실명, 진단명, 가정사 등 민감정보 대신 가상의 페르소나 또는 익명화·일반화된 특성만 사용하는 것을 권장합니다.
- 평가·선발 등 학생에게 영향을 주는 의사결정에 시뮬레이션 결과를 사용해서는 안 됩니다.

## 로드맵

이 프로젝트의 최종 목표는 예측 리포트를 넘어, 페르소나 학생들을 **교실 무대**로 데려와 교사가 실시간으로 수업을 진행하며 상호작용하는 시뮬레이션입니다. 단계별 상세 계획은 **[docs/roadmap.md](docs/roadmap.md)** 를 참고하세요.

## 확장 아이디어

- 같은 단원을 **여러 수업 설계안**(강의식 vs 활동식)으로 시뮬레이션해 비교
- 페르소나에 "지난 수업 결과"를 누적해 학기 단위 시뮬레이션
- Batches API로 대규모(여러 학급 × 여러 단원) 실행 시 비용 50% 절감
- Streamlit 등으로 웹 UI 구성
