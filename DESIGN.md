# 보이는 교실 디자인 시스템

## 0. Research Log

- 기준 시안: 사용자가 선택한 1번 플랫 벡터 SD 시안. 캐릭터의 큰 눈과 부드러운 외곽선, 따뜻한 크림 벽·나무 바닥·초록 칠판을 스타일 기준으로 사용한다.
- 기존 제품: 바닐라 JS 캔버스 교실, 어두운 운영 패널, 4×3 좌석과 학생 상태 오버레이를 그대로 보존한다.
- 적용 범위: 교실 캔버스와 그 안의 에셋만 플랫 벡터로 전환한다. 시안은 화풍 기준이며 앱의 정보 구조를 대체하는 픽셀 단위 레이아웃 기준은 아니다.

## 1. Direction

따뜻한 방과후 교실을 위에서 비스듬히 내려다보는 3/4 시점으로 표현한다. 기억에 남아야 하는 장면은 서로 다른 외형의 SD 학생 12명이 밝은 나무 책상에 앉아 있고, 크림색 교실과 짙은 초록 칠판이 안정된 배경을 만드는 모습이다.

## 2. Color

| 역할 | 토큰 | 값 | 용도 |
|---|---|---|---|
| 교실 벽 | `CLASSROOM_COLORS.cream` | `#F2E8D5` | 벽과 밝은 면 |
| 교실 바닥 | `CLASSROOM_COLORS.floor` | `#C8996B` | 나무 바닥 |
| 나무 밝음 | `CLASSROOM_COLORS.woodLight` | `#D5A56F` | 책상 상판 |
| 나무 기본 | `CLASSROOM_COLORS.wood` | `#A96F45` | 가구 몸체 |
| 나무 외곽 | `CLASSROOM_COLORS.woodDark` | `#79543C` | 외곽선과 깊이 |
| 칠판 | `CLASSROOM_COLORS.board` | `#3E6B4F` | 판면 |
| 잉크 | `CLASSROOM_COLORS.ink` | `#493D39` | 캐릭터 외곽선 |
| 하늘 | `CLASSROOM_COLORS.sky` | `#84BED1` | 창문 |
| 잎 | `CLASSROOM_COLORS.green` | `#6FA77A` | 화분 |
| 이해 | `STATUS_COLORS.comprehension` | `#4DA3FF` | 이해도 막대 |
| 흥미 | `STATUS_COLORS.interest` | `#FFD23F` | 흥미 막대 |
| 집중 | `STATUS_COLORS.focus` | `#5FD97A` | 집중 막대 |
| 강조 | 기존 `--accent` | `#6EE7A0` | 선택·교사·포커스 |

교실 구조는 `CLASSROOM_COLORS`, 상태·텍스트 오버레이는 `STATUS_COLORS`를 사용한다. 학생별 외형 다양성은 `PALETTES`와 `SKIN`, 에셋 부재 시 캐릭터는 `FALLBACK_COLORS`로 한곳에서 관리한다. 반투명은 그림자와 캔버스 오버레이에만 허용한다.

## 3. Typography

- 캔버스 이름표와 판서: `Malgun Gothic`, `Apple SD Gothic Neo`, `Noto Sans KR`, system-ui 순서.
- 기존 운영 UI의 글꼴과 크기 체계는 변경하지 않는다.
- 이름은 모바일 표시 크기 기준 10.5px 이상, 판서는 8px 이상을 유지한다.

## 4. Spacing & Layout

- 실행 토큰: 캔버스는 `CLASSROOM_LAYOUT`, 캔버스 글자 체계는 `CLASSROOM_TYPE`, 반응형 UI는 `--classroom-space-*`, `--classroom-type-*`, `--classroom-touch-*`, `--classroom-radius`, `--classroom-elevation`을 사용한다.
- 캔버스 논리 좌표는 336px 폭, 4열 좌석, 80px 열 간격, 88px 행 간격을 유지한다.
- 에셋 원본은 논리 크기의 4배로 제작하고 캔버스에서 논리 크기로 축소한다.
- 렌더 버퍼는 4배 해상도이며 표시 캔버스는 기기 픽셀 밀도에 맞춰 축소한다.
- 모바일 375px부터 가로 스크롤 없이 교실 전체가 보이고, 이름과 상태 막대가 분리되어야 한다.

## 5. Components

### Classroom Asset
- **Structure**: 투명 RGBA PNG, 타일만 불투명.
- **Variants**: 칠판, 교탁, 학생 책상, 교사, 학생 12명, 감정 8종.
- **States**: 캐릭터 기본/숨쉬기 2프레임, 학생 선택/모둠/감정은 캔버스 오버레이.
- **Accessibility**: 이미지는 캔버스의 ARIA 레이블과 학생 상세 패널로 보완한다.
- **Motion**: 어깨만 논리 1px 올라가는 520ms 숨쉬기. 머리 위치는 고정한다.

### Classroom Canvas
- **Structure**: 고해상도 오프스크린 버퍼 → 화면 캔버스 → 텍스트·상태 오버레이.
- **Variants**: 데스크톱/모바일, 선택/비선택, 말풍선 유무.
- **States**: 포커스, 키보드 이동, 선택, 로딩, 빈 좌석.
- **Accessibility**: 키보드 화살표·Enter·Escape, 가시적 포커스, `role=application`.
- **Motion**: 상태를 전달하는 숨쉬기와 말풍선만 사용한다.

## 6. Motion & Interaction

- 숨쉬기는 2프레임 전환만 사용하며 어깨가 1 논리 px 움직인다.
- 선택과 상태 변화는 기존 상호작용을 유지한다.
- `prefers-reduced-motion`에서는 기존 앱의 비필수 CSS 전환만 제거한다.

## 7. Depth & Surface

- 전략: 플랫 셀 셰이딩과 한 단계의 부드러운 그림자.
- 가구는 밝은 상판, 기본 몸체, 짙은 옆면의 세 면으로 3/4 깊이를 만든다.
- 외곽선은 순수 검정이 아닌 짙은 갈색을 사용한다.

## 8. Accessibility Constraints & Accepted Debt

- 목표: WCAG 2.2 AA, 터치 대상 40px 이상, 모든 핵심 작업의 키보드 접근 유지.
- 캔버스 내부 글자는 고대비 외곽선을 사용한다.
- 새로 수용한 접근성 부채는 없다.
