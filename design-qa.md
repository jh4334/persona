# 1번 플랫 벡터 SD 교실 QA

## 대상

- 기준 시안: 사용자가 선택한 1번 플랫 벡터 SD 스타일
- 구현 기준: 현재 브랜치 HEAD
- 데스크톱 캡처: `qa-evidence/vector-flat/desktop.png` (`2000×1406`, PNG)
- 모바일 캡처: `qa-evidence/vector-flat/mobile.png` (`610×1135`, PNG)
- 공유용 교실 캡처: `docs/vector-classroom-mobile.png` (`609×690`, PNG)

## 결과

| 항목 | 결과 | 확인 내용 |
|---|---|---|
| 18개 에셋 계약 | PASS | 규격, RGBA, 타일 불투명, 나머지 투명 배경 |
| 캐릭터 애니메이션 | PASS | 교사와 학생 12명 모두 서로 다른 2프레임 |
| 실사용 렌더링 | PASS | 타일, 칠판, 책상, 캐릭터, 감정 에셋을 라이브 캔버스에서 사용 |
| 스타일 충실도 | PASS | 따뜻한 크림·나무·초록 팔레트와 플랫 벡터 SD 표현 |
| 한글 가독성 | PASS | 학생 이름 12개와 교사 이름표에 깨진 글자 없음 |
| 상태 정보 | PASS | 학생마다 이해·흥미·집중 3개 게이지 분리 표시 |
| 모바일 레이아웃 | PASS | 툴바 가로 스크롤 없음, 입력창과 보내기 버튼 잘림 없음 |
| 보안·코드 품질 | PASS | 새 비밀정보·동적 실행·외부 에셋 로딩 없음, 차단 이슈 없음 |

## 검증

- `python -m unittest tests.test_vector_assets -v`: 3/3 PASS
- `node --check src/classroom_sim/web/static/app.js`: PASS
- `PYTHONUTF8=1 python tests/regression/test_cycle18.py`: PASS
- 독립 목표 검토, 실행 QA, 코드 품질, 보안, 맥락 검토: 5/5 PASS
- 독립 디자인 시스템 검토와 시각/CJK 검토: 2/2 PASS

## 남은 비차단 사항

- 레거시 `docs/asset_request.md`는 원래 픽셀 에셋 규격을 기록하고, 새 벡터 에셋 계약은 `DESIGN.md`와 에셋 README에 병렬로 기록한다.
- 실제 iOS Safari 물리 기기 검증은 수행하지 않았고, 브라우저의 모바일 뷰포트에서 레이아웃을 확인했다.
