/* ============================================================
   보이는 교실 — 프론트엔드 (바닐라 JS, 외부 라이브러리·CDN 없음)

   구성
     1) API 래퍼        : 턴 단위 fetch (웹소켓 불필요)
     2) 에셋 로더        : /static/assets/vector/ 의 PNG를 시도하고, 없으면 코드로 그린
                          픽셀 폴백 스프라이트를 사용 (콘솔 경고 없음)
     3) 캔버스 무대      : 336×256 논리 캔버스를 4배 버퍼에서 부드럽게 렌더링
     4) UI 바인딩        : 셋업 / 무대 / 종료 리포트 3화면
     5) 미니 마크다운 렌더러 (리포트용, 외부 라이브러리 금지라 직접 구현)
   ============================================================ */
'use strict';

/* ══════════════════════════ 0. 설정 ══════════════════════════ */

const CLASSROOM_LAYOUT = Object.freeze({
  columns: 4, logicalWidth: 336, deskWidth: 40, deskHeight: 40,
  columnCenters: Object.freeze([48, 128, 208, 288]), rowStart: 110, rowGap: 88,
  spriteWidth: 32, spriteHeight: 48, wallHeight: 46, assetScale: 4, renderScale: 4,
  deskBackHeight: 12, seatBottomOffset: 22,
});
const {
  columns: COLS, logicalWidth: LOGICAL_W, deskWidth: DESK_W, deskHeight: DESK_H,
  columnCenters: COL_X, rowStart: ROW_Y0, rowGap: ROW_GAP,
  spriteWidth: SPRITE_W, spriteHeight: SPRITE_H, wallHeight: WALL_H,
  assetScale: ASSET_SCALE, renderScale: RENDER_SCALE,
  deskBackHeight: DESK_BACK_H, seatBottomOffset: SEAT_BOTTOM_OFFSET,
} = CLASSROOM_LAYOUT;

const ASSET_BASE = '/static/assets/vector/';
const BUBBLE_MS = 6000;               // 말풍선 유지 시간
const TRANSCRIPT_MAX = 400;           // 전사 로그 DOM 상한 (전체 기록은 서버가 보관)
const CANVAS_FONT = '"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif';
const CLASSROOM_TYPE = Object.freeze({
  board: Object.freeze({ base: 3.4, min: 8, line: 4.2 }),
  teacher: Object.freeze({ base: 3.2, min: 8 }),
  studentName: Object.freeze({ base: 4.8, min: 10.5 }),
  emoteFallback: Object.freeze({ base: 6, min: 12 }),
  sleepCue: Object.freeze({ base: 3.6, min: 8 }),
  bubble: Object.freeze({ base: 3.6, min: 10.5, clampMin: 11, clampMax: 18 }),
});

// 감정 → 이모지 (에셋 emotes.png가 있으면 시트 인덱스를 우선 사용)
const EMOTION_ORDER = ['손듦', '졸림', '혼란', '몰입', '불안', '수다', '지루함', '흥분'];
const EMOTION_EMOJI = {
  '평온': '😌', '들뜸': '✨', '위축': '😟', '불안': '😰', '지루함': '🥱',
  '몰입': '🤩', '졸림': '😴', '손듦': '🙋', '수다': '💬', '피곤': '😴', '흥분': '✨',
  '짜증': '😠', '슬픔': '😢', '자신감': '😎', '혼란': '😕',
};

// 학생별 고유 색상 팔레트 (폴백 스프라이트용) — 머리/옷/바지
const PALETTES = [
  { hair: '#3b2314', shirt: '#e05c5c', pants: '#33436b' },
  { hair: '#1f1a17', shirt: '#4f8ef7', pants: '#2f2f3d' },
  { hair: '#5a3720', shirt: '#f2c14e', pants: '#40506e' },
  { hair: '#2b2b2b', shirt: '#59c28b', pants: '#3a3f52' },
  { hair: '#6b3f1d', shirt: '#c46be0', pants: '#2c3a5a' },
  { hair: '#111111', shirt: '#f08a3c', pants: '#37485f' },
  { hair: '#4a2c17', shirt: '#7fd1e8', pants: '#3d3355' },
  { hair: '#2f1d10', shirt: '#8bd45a', pants: '#4a3a2a' },
  { hair: '#7a4a22', shirt: '#f277a8', pants: '#33436b' },
  { hair: '#1a1a24', shirt: '#a58cf0', pants: '#2e3d33' },
  { hair: '#513017', shirt: '#f6e07a', pants: '#3b4a63' },
  { hair: '#241611', shirt: '#57b7a8', pants: '#4b3550' },
];
const SKIN = ['#f6d3b0', '#e8bd94', '#d9a577'];
const GROUP_COLORS = ['#ff8f4d', '#4dd0ff', '#b48cff', '#8bdc5a', '#ff7ab6', '#ffd54d'];
const CLASSROOM_COLORS = Object.freeze({
  floor: '#C8996B', floorDark: '#A8734F', cream: '#F2E8D5', creamShade: '#DCCCAD',
  board: '#3E6B4F', boardLight: '#5C836A', wood: '#A96F45', woodLight: '#D5A56F',
  woodDark: '#79543C', sky: '#84BED1', green: '#6FA77A', blue: '#6F9CC4',
  blueDark: '#486E98', pink: '#D9899E', yellow: '#E8C568', white: '#FFFDF5', ink: '#493D39',
});
const STATUS_COLORS = Object.freeze({
  comprehension: '#4DA3FF', interest: '#FFD23F', focus: '#5FD97A', selected: '#FFE066',
  gaugeBackdrop: 'rgba(20,16,10,.55)', gaugeTrack: '#2C2216', name: '#FDF6E6',
  labelBackdrop: 'rgba(0,0,0,.35)', labelStroke: 'rgba(0,0,0,.7)', boardText: '#EEF4EA',
  teacherLabel: '#FFE9B0', sleepCue: '#CFD8FF',
  bubbleInk: '#14161D', bubblePaper: '#FBF8EF', bubbleText: '#1B1E28',
});
const FALLBACK_COLORS = Object.freeze({
  teacherHair: '#20242E', teacherShirt: '#5B6B8C', teacherPants: '#2B303D', ink: '#1A1420',
  shoe: '#2A2A33', mouth: '#A5525A', blush: 'rgba(230,120,120,.55)',
  collar: '#E8EBF5', ruler: '#D9C08A',
});

/* ══════════════════════════ 1. 앱 상태 ══════════════════════════ */

const App = {
  sessionId: null,
  className: '',
  lessonTitle: '',
  backend: 'mock',
  students: [],           // [{id,name,achievement_level,...}] 좌석 순서
  personas: {},           // id → 페르소나 요약
  states: {},             // id → {comprehension,interest,focus,emotion,visible_action}
  groups: {},             // id → 모둠 번호
  bubbles: [],            // [{sid,text,t0}]
  boardText: '',          // 칠판에 남길 마지막 판서 내용
  selected: null,
  turn: 0, minute: 0, phase: '도입', ended: false,
  busy: false,
  reportMd: '',
  seatOf: {},             // id → 좌석 index
};

const $ = (sel) => document.querySelector(sel);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/** 모바일 모드 여부 — style.css의 미디어 쿼리와 동일한 조건을 쓴다 */
const MOBILE_MQ = '(max-width: 820px), (max-width: 950px) and (max-height: 500px) and (orientation: landscape)';
const isMobile = () => window.matchMedia(MOBILE_MQ).matches;

/* ══════════════════════════ 2. API ══════════════════════════ */

const API_TIMEOUT_MS = 320000;   // 느린 백엔드(codex) 감안 + 서버 타임아웃(300s)보다 여유

async function api(path, options) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), API_TIMEOUT_MS);
  let res;
  try {
    res = await fetch(path, Object.assign(
      { headers: { 'Content-Type': 'application/json' }, signal: ctrl.signal }, options));
  } catch (e) {
    clearTimeout(timer);
    let err;
    if (e.name === 'AbortError') {
      err = new Error('응답이 너무 오래 걸려 요청을 중단했습니다.');
      err.code = 'timeout';
    } else if (navigator.onLine === false) {
      err = new Error('인터넷 연결이 끊어져 있습니다. Wi-Fi 연결을 확인해 주세요.');
      err.code = 'network';
    } else {
      err = new Error('서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.');
      err.code = 'network';
    }
    throw err;
  }
  clearTimeout(timer);
  if (!res.ok) {
    let detail = res.status + ' ' + res.statusText;
    try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (e) { /* 무시 */ }
    const err = new Error(detail);
    err.code = res.status;
    throw err;
  }
  return res.json();
}

const Api = {
  classrooms: () => api('/api/classrooms'),
  lessons: () => api('/api/lessons'),
  createSession: (body) => api('/api/sessions', { method: 'POST', body: JSON.stringify(body) }),
  turn: (id, input) => api(`/api/sessions/${id}/turn`, { method: 'POST', body: JSON.stringify({ input }) }),
  state: (id) => api(`/api/sessions/${id}/state`),
  transcript: (id) => api(`/api/sessions/${id}/transcript`),
  end: (id) => api(`/api/sessions/${id}/end`, { method: 'POST' }),
};

/* ══════════════════════════ 3. 에셋 로더 ══════════════════════════

   규약대로 PNG가 있으면 그걸 쓰고, 404면 조용히 폴백 스프라이트를 쓴다.
   (<img>의 onerror는 브라우저가 콘솔에 네트워크 오류를 남기므로 fetch로 확인한다.)
   ============================================================== */

const Assets = {
  images: {},   // 이름 → ImageBitmap | null
  sprites: {},  // 이름 → {img, frames, w, h, fallback:boolean}

  async tryLoad(name, file) {
    try {
      const res = await fetch(ASSET_BASE + file, { cache: 'force-cache' });
      if (!res.ok) return null;
      const blob = await res.blob();
      if (!blob.size || !/image/.test(blob.type || 'image')) return null;
      return await createImageBitmap(blob);
    } catch (e) {
      return null; // 콘솔 경고 없이 폴백
    }
  },

  async loadAll(studentCount) {
    const jobs = [
      ['tiles', 'tiles.png'],
      ['blackboard', 'blackboard.png'],
      ['desk_student', 'desk_student.png'],
      ['desk_teacher', 'desk_teacher.png'],
      ['char_teacher', 'char_teacher.png'],
      ['emotes', 'emotes.png'],
    ];
    for (let i = 1; i <= studentCount; i++) {
      const n = String(i).padStart(2, '0');
      jobs.push(['char_s' + n, `char_s${n}.png`]);
    }
    await Promise.all(jobs.map(async ([name, file]) => {
      Assets.images[name] = await Assets.tryLoad(name, file);
    }));
  },

  /** 캐릭터 스프라이트 얻기: PNG 우선, 없으면 팔레트 기반 폴백 시트 생성 */
  character(key, paletteIndex, isTeacher) {
    if (Assets.sprites[key]) return Assets.sprites[key];
    const png = Assets.images[key];
    let sprite;
    if (png) {
      sprite = {
        img: png,
        frames: Math.max(1, Math.round(png.width / (SPRITE_W * ASSET_SCALE))),
        sourceScale: ASSET_SCALE,
        fallback: false,
      };
    } else {
      sprite = {
        img: buildFallbackSheet(paletteIndex, isTeacher), frames: 3, sourceScale: 1, fallback: true,
      };
    }
    Assets.sprites[key] = sprite;
    return sprite;
  },
};

/* ── 폴백 스프라이트: 32×48 도트 캐릭터를 코드로 그린다 ──────────────
   시트 구성: [frame0 idle] [frame1 idle(1px 흔들림)] [frame2 슬럼프(집중 낮음)]
   순수 fillRect(정수 좌표)만 사용해 픽셀 느낌을 유지한다.            */
function buildFallbackSheet(paletteIndex, isTeacher) {
  const cv = document.createElement('canvas');
  cv.width = SPRITE_W * 3;
  cv.height = SPRITE_H;
  const g = cv.getContext('2d');
  for (let f = 0; f < 3; f++) {
    g.save();
    g.translate(f * SPRITE_W, 0);
    drawFallbackChar(g, paletteIndex, f, isTeacher);
    g.restore();
  }
  return cv;
}

function drawFallbackChar(g, paletteIndex, frame, isTeacher) {
  const pal = isTeacher
    ? { hair: FALLBACK_COLORS.teacherHair, shirt: FALLBACK_COLORS.teacherShirt, pants: FALLBACK_COLORS.teacherPants }
    : PALETTES[paletteIndex % PALETTES.length];
  const skin = SKIN[paletteIndex % SKIN.length];
  const ink = FALLBACK_COLORS.ink;              // 외곽선
  const bob = frame === 1 ? 1 : 0;             // idle 2프레임 흔들림
  const slump = frame === 2;                   // 집중 낮음: 몸을 기울인 자세
  const dx = slump ? 2 : 0;
  const dy = (slump ? 3 : 0) + bob;

  const R = (x, y, w, h, c) => { g.fillStyle = c; g.fillRect(Math.round(x), Math.round(y), w, h); };
  // 외곽선을 먼저 깔고 그 위에 색을 얹어 1px 테두리를 만든다
  const B = (x, y, w, h, c) => { R(x - 1, y - 1, w + 2, h + 2, ink); R(x, y, w, h, c); };

  // 다리·신발 (책상에 가려 거의 보이지 않지만 서 있는 교사용으로 필요)
  B(11, 36, 5, 10, pal.pants);
  B(17, 36, 5, 10, pal.pants);
  R(10, 45, 7, 2, FALLBACK_COLORS.shoe);
  R(16, 45, 7, 2, FALLBACK_COLORS.shoe);

  // 몸통
  B(8 + dx, 21 + dy, 16, 15, pal.shirt);
  // 팔
  B(5 + dx, 23 + dy, 3, 11, pal.shirt);
  B(24 + dx, 23 + dy, 3, 11, pal.shirt);
  R(5 + dx, 33 + dy, 3, 3, skin);
  R(24 + dx, 33 + dy, 3, 3, skin);

  // 목 · 머리
  R(14 + dx, 19 + dy, 4, 3, skin);
  B(9 + dx, 6 + dy, 14, 14, skin);
  // 머리카락
  R(8 + dx, 4 + dy, 16, 6, pal.hair);
  R(8 + dx, 10 + dy, 2, 5, pal.hair);
  R(22 + dx, 10 + dy, 2, 5, pal.hair);
  R(9 + dx, 3 + dy, 14, 1, pal.hair);

  // 눈 (슬럼프면 감은 눈 —)
  if (slump) {
    R(12 + dx, 14 + dy, 3, 1, ink);
    R(18 + dx, 14 + dy, 3, 1, ink);
  } else {
    R(12 + dx, 13 + dy, 2, 2, ink);
    R(18 + dx, 13 + dy, 2, 2, ink);
  }
  // 입
  R(14 + dx, 17 + dy, 4, 1, FALLBACK_COLORS.mouth);
  // 볼 터치
  R(10 + dx, 15 + dy, 2, 1, FALLBACK_COLORS.blush);
  R(21 + dx, 15 + dy, 2, 1, FALLBACK_COLORS.blush);

  if (isTeacher) { // 교사 표식: 옷깃 + 손에 든 자
    R(13, 21 + dy, 6, 2, FALLBACK_COLORS.collar);
    R(26, 22 + dy, 2, 12, FALLBACK_COLORS.ruler);
  }
}

/* ══════════════════════════ 4. 무대 렌더러 ══════════════════════════ */

const Stage = {
  canvas: null, ctx: null,
  buf: null, bctx: null,          // 논리 해상도 오프스크린 버퍼
  scale: 3,
  W: LOGICAL_W, H: 256,
  rafId: 0,

  init() {
    Stage.canvas = $('#classroom');
    Stage.ctx = Stage.canvas.getContext('2d');
    Stage.buf = document.createElement('canvas');
    Stage.bctx = Stage.buf.getContext('2d');
    // 새 수업으로 init이 다시 불려도 전역 리스너·rAF 루프는 한 번만 등록한다
    if (!Stage._wired) {
      Stage._wired = true;
      Stage.canvas.addEventListener('click', Stage.onClick);
      Stage.canvas.addEventListener('keydown', Stage.onKey);
      window.addEventListener('resize', Stage.resize);
      window.addEventListener('orientationchange', () => setTimeout(Stage.resize, 250));
      // 탭이 다시 보이면 강제로 한 프레임 그린다 (숨김 중 상태 변화 반영)
      document.addEventListener('visibilitychange', () => { if (!document.hidden) Stage.dirty = true; });
      const loop = () => { Stage.draw(); Stage.rafId = requestAnimationFrame(loop); };
      Stage.rafId = requestAnimationFrame(loop);
    }
    Stage.layout();
    Stage.resize();
    // 첫 배치 직후 CSS가 확정된 표시 크기로 한 번 더 맞춘다 (모바일 해상도 선택용)
    requestAnimationFrame(() => Stage.resize());
  },

  /** 학생 수에 맞춰 논리 캔버스 높이를 정한다 (4열 기준) */
  layout() {
    const rows = Math.max(1, Math.ceil(App.students.length / COLS));
    Stage.W = LOGICAL_W;
    Stage.H = ROW_Y0 + ROW_GAP * (rows - 1) + DESK_H + 32;
    Stage.buf.width = Stage.W * RENDER_SCALE;
    Stage.buf.height = Stage.H * RENDER_SCALE;
    Stage.bctx.setTransform(RENDER_SCALE, 0, 0, RENDER_SCALE, 0, 0);
    Stage.dirty = true;
  },

  seat(i) {
    const col = i % COLS, row = Math.floor(i / COLS);
    const cx = COL_X[col];
    const deskTop = ROW_Y0 + row * ROW_GAP;
    return {
      cx,
      deskTop,
      spriteX: cx - SPRITE_W / 2,
      spriteY: deskTop + SEAT_BOTTOM_OFFSET - SPRITE_H,
    };
  },

  resize() {
    const wrap = $('#canvas-wrap');
    if (!wrap) return;
    let s;
    if (isMobile()) {
      // 모바일: 표시 크기는 CSS(max-width/max-height)가 정하므로 화면 밀도에 맞는 내부 해상도만 고른다.
      // 내부 해상도는 항상 표시 크기보다 크게 유지되어 CSS 제약이 흔들리지 않는다.
      const cssW = Math.max(160, Stage.canvas.clientWidth || wrap.clientWidth);
      const dpr = clamp(window.devicePixelRatio || 1, 1, 3);
      s = Math.round(cssW * dpr / Stage.W);
    } else {
      const availW = wrap.clientWidth - 20, availH = wrap.clientHeight - 20;
      s = Math.floor(Math.min(availW / Stage.W, availH / Stage.H));
    }
    Stage.scale = clamp(Math.max(1, s), 2, 6);
    Stage.canvas.width = Stage.W * Stage.scale;
    Stage.canvas.height = Stage.H * Stage.scale;
    Stage.dirty = true;
  },

  /** 키보드로 학생 선택 — 화살표로 이동, Enter/Space로 카드, Escape로 해제 */
  onKey(ev) {
    const n = App.students.length;
    if (!n) return;
    const cur = App.selected ? App.students.findIndex((s) => s.id === App.selected) : -1;
    let next = cur;
    if (ev.key === 'ArrowRight') next = cur < 0 ? 0 : Math.min(n - 1, cur + 1);
    else if (ev.key === 'ArrowLeft') next = cur < 0 ? 0 : Math.max(0, cur - 1);
    else if (ev.key === 'ArrowDown') next = cur < 0 ? 0 : Math.min(n - 1, cur + COLS);
    else if (ev.key === 'ArrowUp') next = cur < 0 ? 0 : Math.max(0, cur - COLS);
    else if (ev.key === 'Escape') { UI.selectStudent(null); ev.preventDefault(); return; }
    else if ((ev.key === 'Enter' || ev.key === ' ') && cur >= 0) { ev.preventDefault(); return; }
    else return;
    ev.preventDefault();
    if (next !== cur) UI.selectStudent(App.students[next].id);
  },

  onClick(ev) {
    const r = Stage.canvas.getBoundingClientRect();
    const x = (ev.clientX - r.left) / r.width * Stage.W;
    const y = (ev.clientY - r.top) / r.height * Stage.H;
    for (let i = 0; i < App.students.length; i++) {
      const s = Stage.seat(i);
      if (x >= s.cx - 24 && x <= s.cx + 24 && y >= s.spriteY - 4 && y <= s.deskTop + DESK_H + 12) {
        UI.selectStudent(App.students[i].id);
        return;
      }
    }
    UI.selectStudent(null);
  },

  drawTile(g, index, x, y, width = 32, height = 32) {
    const sourceSize = 32 * ASSET_SCALE;
    g.drawImage(
      Assets.images.tiles,
      index * sourceSize,
      0,
      sourceSize,
      sourceSize,
      x,
      y,
      width,
      height,
    );
  },

  /* ── 배경(교실) ── */
  drawRoom(g) {
    const W = Stage.W, H = Stage.H;
    const colors = CLASSROOM_COLORS;
    if (Assets.images.tiles) {
      for (let y = WALL_H, row = 0; y < H; y += 32, row++) {
        for (let x = 0, col = 0; x < W; x += 32, col++) {
          Stage.drawTile(g, (row + col) % 5 === 0 ? 1 : 0, x, y);
        }
      }
      g.save();
      g.beginPath(); g.rect(0, 0, W, WALL_H); g.clip();
      for (let y = 0; y < WALL_H; y += 32) {
        for (let x = 0; x < W; x += 32) Stage.drawTile(g, 2, x, y);
      }
      g.restore();
    } else {
      g.fillStyle = colors.floor; g.fillRect(0, WALL_H, W, H - WALL_H);
      g.fillStyle = colors.cream; g.fillRect(0, 0, W, WALL_H);
    }
    g.fillStyle = colors.woodLight; g.fillRect(0, WALL_H - 4, W, 4);
    g.fillStyle = colors.woodDark; g.fillRect(0, WALL_H - 1, W, 1);

    if (Assets.images.blackboard) {
      g.drawImage(Assets.images.blackboard, 92, 6, 192, 64);
    } else {
      g.fillStyle = colors.woodDark; g.fillRect(92, 6, 152, 34);
      g.fillStyle = colors.wood; g.fillRect(92, 36, 152, 4);
      g.fillStyle = colors.board; g.fillRect(95, 9, 146, 25);
      g.fillStyle = colors.boardLight; g.fillRect(95, 9, 146, 2);
      g.fillStyle = colors.white; g.fillRect(97, 37, 6, 2); g.fillRect(105, 37, 4, 2);
    }
    if (Assets.images.tiles) {
      Stage.drawTile(g, 3, 8, 7, 40, 32);
      Stage.drawTile(g, 4, 286, 6, 42, 34);
      Stage.drawTile(g, 6, 10, 50, 28, 28);
      Stage.drawTile(g, 5, 304, 50, 28, 28);
    } else {
      g.fillStyle = colors.white; g.fillRect(8, 8, 40, 30);
      g.fillStyle = colors.sky; g.fillRect(11, 11, 34, 24);
      g.fillStyle = colors.woodDark; g.fillRect(286, 6, 42, 34);
      g.fillStyle = colors.woodLight; g.fillRect(289, 9, 36, 28);
      g.fillStyle = colors.green; g.fillRect(16, 52, 12, 17);
      g.fillStyle = colors.blue; g.fillRect(306, 52, 24, 26);
    }
    g.fillStyle = colors.white; g.fillRect(262, 12, 12, 12);
    g.fillStyle = colors.ink; g.fillRect(267, 14, 1, 5); g.fillRect(267, 18, 4, 1);

    if (Assets.images.desk_teacher) {
      g.drawImage(Assets.images.desk_teacher, 148, 50, 64, 48);
    } else {
      g.fillStyle = colors.woodDark; g.fillRect(148, 50, 56, 18);
      g.fillStyle = colors.woodLight; g.fillRect(148, 50, 56, 5);
      g.fillStyle = colors.ink; g.fillRect(152, 68, 4, 4); g.fillRect(196, 68, 4, 4);
    }
  },

  drawDesk(g, s, sid, layer) {
    const x = s.cx - DESK_W / 2, y = s.deskTop;
    if (Assets.images.desk_student) {
      const desk = Assets.images.desk_student;
      const sourceSplit = DESK_BACK_H * ASSET_SCALE;
      if (layer === 'back') {
        g.drawImage(desk, 0, 0, desk.width, sourceSplit, x, y, DESK_W, DESK_BACK_H);
      } else {
        g.drawImage(
          desk,
          0,
          sourceSplit,
          desk.width,
          desk.height - sourceSplit,
          x,
          y + DESK_BACK_H,
          DESK_W,
          DESK_H - DESK_BACK_H,
        );
      }
    } else {
      const colors = CLASSROOM_COLORS;
      if (layer === 'back') {
        g.fillStyle = colors.woodDark; g.fillRect(x + 11, y + 2, 18, 10);
        g.fillStyle = colors.wood; g.fillRect(x + 13, y + 4, 14, 7);
      } else {
        g.fillStyle = colors.ink; g.fillRect(x - 1, y + DESK_BACK_H - 1, DESK_W + 2, DESK_H - DESK_BACK_H + 2);
        g.fillStyle = colors.woodLight; g.fillRect(x, y + DESK_BACK_H, DESK_W, 7);
        g.fillStyle = colors.wood; g.fillRect(x, y + DESK_BACK_H + 7, DESK_W, 5);
        g.fillStyle = colors.woodDark; g.fillRect(x + 3, y + DESK_BACK_H + 12, 4, DESK_H - DESK_BACK_H - 12);
        g.fillRect(x + DESK_W - 7, y + DESK_BACK_H + 12, 4, DESK_H - DESK_BACK_H - 12);
      }
    }
    if (layer === 'back') return;
    // 모둠 테두리
    const grp = App.groups[sid];
    if (grp) {
      g.strokeStyle = GROUP_COLORS[(grp - 1) % GROUP_COLORS.length];
      g.lineWidth = 1;
      g.strokeRect(x - 2.5, y - 2.5, DESK_W + 5, DESK_H + 5);
    }
    // 선택 표시
    if (App.selected === sid) {
      g.strokeStyle = STATUS_COLORS.selected; g.lineWidth = 1;
      g.strokeRect(x - 4.5, s.spriteY - 4.5, DESK_W + 9, s.deskTop + DESK_H + 4 - s.spriteY + 5);
    }
  },

  drawGauges(g, s, st) {
    const bars = [
      [st.comprehension, STATUS_COLORS.comprehension],
      [st.interest, STATUS_COLORS.interest],
      [st.focus, STATUS_COLORS.focus],
    ];
    const w = 26, x = s.cx - w / 2;
    let y = s.deskTop + DESK_H + 5;
    bars.forEach(([v, c]) => {
      g.fillStyle = STATUS_COLORS.gaugeBackdrop; g.fillRect(x - 1, y - 1, w + 2, 4);
      g.fillStyle = STATUS_COLORS.gaugeTrack; g.fillRect(x, y, w, 2);
      g.fillStyle = c; g.fillRect(x, y, Math.round(w * clamp(v, 0, 100) / 100), 2);
      y += 4;
    });
  },

  drawCharacter(g, sprite, x, y, frame) {
    const f = Math.min(frame, sprite.frames - 1);
    const sourceScale = sprite.sourceScale || 1;
    const sourceW = SPRITE_W * sourceScale, sourceH = SPRITE_H * sourceScale;
    g.drawImage(sprite.img, f * sourceW, 0, sourceW, sourceH, x, y, SPRITE_W, SPRITE_H);
  },

  emotionKey(st) {
    if (!st) return '평온';
    const e = st.emotion || '평온';
    if (EMOTION_EMOJI[e]) return e;
    if (st.focus < 30) return '졸림';
    return '평온';
  },

  draw() {
    const g = Stage.bctx;
    if (!g || document.body.dataset.screen !== 'stage') return;   // 무대 화면일 때만 그린다
    const t = performance.now();
    const frameIdle = Math.floor(t / 520) % 2;   // 2프레임 idle
    // 변한 게 없으면 그리지 않는다 — idle은 520ms, zzz는 700ms에 한 번만 바뀌므로
    // 말풍선이 없을 때는 사실상 초당 2~3회만 그린다 (모바일 배터리·발열 절감)
    const zFrame = Math.floor(t / 700) % 2;
    const hasBubble = App.bubbles.some((b) => t - b.t0 < BUBBLE_MS);
    if (!Stage.dirty && !hasBubble && !Stage._hadBubble
        && frameIdle === Stage._idleF && zFrame === Stage._zF) return;
    Stage.dirty = false;
    Stage._idleF = frameIdle; Stage._zF = zFrame; Stage._hadBubble = hasBubble;

    g.imageSmoothingEnabled = true;
    g.clearRect(0, 0, Stage.W, Stage.H);
    Stage.drawRoom(g);

    // 교사
    const teacher = Assets.character('char_teacher', 5, true);
    Stage.drawCharacter(g, teacher, 112, 50 + 8 - SPRITE_H, frameIdle);

    // 학생: 뒤 → 앞 순서로 그려야 앞줄이 위에 겹친다
    App.students.forEach((stu, i) => {
      const s = Stage.seat(i);
      const st = App.states[stu.id] || {};
      const sprite = Assets.character('char_s' + String(i + 1).padStart(2, '0'), i, false);
      // 집중이 낮으면 슬럼프 프레임(폴백 시트에만 존재)
      const low = (st.focus !== undefined && st.focus < 35);
      const frame = low && sprite.frames > 2 ? 2 : frameIdle;
      Stage.drawDesk(g, s, stu.id, 'back');
      Stage.drawCharacter(g, sprite, s.spriteX, s.spriteY, frame);
      Stage.drawDesk(g, s, stu.id, 'front');
      Stage.drawGauges(g, s, st);
    });

    const ctx = Stage.ctx, S = Stage.scale;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.clearRect(0, 0, Stage.canvas.width, Stage.canvas.height);
    ctx.drawImage(Stage.buf, 0, 0, Stage.W * S, Stage.H * S);

    // 캔버스 내부 픽셀 ÷ 실제 표시 CSS 픽셀. 모바일에서 글자 최소 크기를 보정하는 데만 쓴다.
    // 데스크톱은 0으로 두어 아래 글자 크기 계산이 기존 식과 완전히 동일해진다(회귀 방지).
    const shownW = Stage.canvas.clientWidth || Stage.canvas.width;
    Stage.K = isMobile() ? Stage.canvas.width / Math.max(1, shownW) : 0;

    Stage.drawOverlay(ctx, S, t);
  },

  /** 텍스트류(이름·말풍선·이모지·판서)는 화면 해상도로 그려야 읽을 수 있다 */
  drawOverlay(ctx, S, t) {
    const K = Stage.K || 0;
    // 표시 기준(CSS 픽셀) 최소 글자 크기를 보장한다.
    // 데스크톱은 K=0이라 항상 base*S(기존 식)가 그대로 쓰이고, 모바일에서만 글자가 커진다.
    const F = (base, minCss) => Math.round(Math.max(base * S, minCss * K));
    // 판서 내용 (칠판 위)
    if (App.boardText) {
      const bf = F(CLASSROOM_TYPE.board.base, CLASSROOM_TYPE.board.min);
      ctx.save();
      ctx.beginPath(); ctx.rect(96 * S, 10 * S, 184 * S, 24 * S); ctx.clip();
      ctx.font = `${bf}px ${CANVAS_FONT}`;
      ctx.fillStyle = STATUS_COLORS.boardText; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      wrapText(ctx, App.boardText, 188 * S, 12 * S, 178 * S, Math.max(CLASSROOM_TYPE.board.line * S, bf * 1.24), 3);
      ctx.restore();
    }
    // 교사 이름표
    const tf = F(CLASSROOM_TYPE.teacher.base, CLASSROOM_TYPE.teacher.min);
    ctx.font = `${tf}px ${CANVAS_FONT}`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const tw = Math.max(32 * S, ctx.measureText('교사').width + tf);
    const th = Math.max(6 * S, tf * 1.4);
    ctx.fillStyle = STATUS_COLORS.labelBackdrop;
    ctx.fillRect(128 * S - tw / 2, 60 * S, tw, th);
    ctx.fillStyle = STATUS_COLORS.teacherLabel;
    ctx.fillText('교사', 128 * S, 60 * S + (th - tf) / 2);

    App.students.forEach((stu, i) => {
      const s = Stage.seat(i);
      const st = App.states[stu.id] || {};
      // 이름표
      const ny = (s.deskTop + 25) * S;
      ctx.font = `${F(CLASSROOM_TYPE.studentName.base, CLASSROOM_TYPE.studentName.min)}px ${CANVAS_FONT}`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      ctx.fillStyle = App.selected === stu.id ? STATUS_COLORS.selected : STATUS_COLORS.name;
      ctx.strokeStyle = STATUS_COLORS.labelStroke; ctx.lineWidth = Math.max(2, S * 0.7);
      ctx.strokeText(stu.name, s.cx * S, ny);
      ctx.fillText(stu.name, s.cx * S, ny);

      // 감정 아이콘 (아바타 머리 위)
      const ex = (s.cx + 9) * S, ey = (s.spriteY - 2) * S;
      const key = Stage.emotionKey(st);
      const idx = EMOTION_ORDER.indexOf(key);
      if (Assets.images.emotes && idx >= 0) {
        const es = Math.max(12 * S, 22 * K);
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(
          Assets.images.emotes,
          idx * 16 * ASSET_SCALE,
          0,
          16 * ASSET_SCALE,
          16 * ASSET_SCALE,
          ex - es / 2,
          ey - es * 0.67,
          es,
          es,
        );
      } else {
        ctx.font = `${F(CLASSROOM_TYPE.emoteFallback.base, CLASSROOM_TYPE.emoteFallback.min)}px ${CANVAS_FONT}`;
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        ctx.fillText(EMOTION_EMOJI[key] || '😐', ex - 3 * S, ey + 2 * S);
      }
      // 집중 급락 시 zzz
      if (st.focus !== undefined && st.focus < 25 && Math.floor(t / 700) % 2 === 0) {
        ctx.font = `${F(CLASSROOM_TYPE.sleepCue.base, CLASSROOM_TYPE.sleepCue.min)}px ${CANVAS_FONT}`;
        ctx.fillStyle = STATUS_COLORS.sleepCue; ctx.textAlign = 'left';
        ctx.fillText('z z', (s.cx - 18) * S, (s.spriteY + 4) * S);
      }
    });

    // 말풍선 (최근 3개)
    const live = App.bubbles.filter((b) => t - b.t0 < BUBBLE_MS).slice(-3);
    App.bubbles = App.bubbles.filter((b) => t - b.t0 < BUBBLE_MS);
    live.forEach((b) => {
      const i = App.seatOf[b.sid];
      if (i === undefined) return;
      const s = Stage.seat(i);
      const age = t - b.t0;
      ctx.globalAlpha = age > BUBBLE_MS - 1200 ? clamp((BUBBLE_MS - age) / 1200, 0, 1) : 1;
      drawBubble(ctx, S, K, s.cx * S, (s.spriteY - 10) * S, b.text);
      ctx.globalAlpha = 1;
    });
  },
};

/** 픽셀풍 말풍선 (꼬리 포함). x=꼬리 중심, yBottom=꼬리 끝 y
    K = 캔버스 내부 픽셀 / 표시 CSS 픽셀 (데스크톱 1, 모바일 >1) */
function drawBubble(ctx, S, K, x, yBottom, text) {
  const bubbleType = CLASSROOM_TYPE.bubble;
  const fs = Math.max(
    clamp(Math.round(bubbleType.base * S), bubbleType.clampMin, bubbleType.clampMax),
    Math.round(bubbleType.min * K),
  );
  ctx.font = `${fs}px ${CANVAS_FONT}`;
  // 모바일에서는 글자를 키우는 대신 폭도 넓히되, 무대를 다 가리지 않도록 캔버스의 60%로 제한
  const maxW = Math.min(Math.max(clamp(110 * S, 140, 300), 150 * K), ctx.canvas.width * 0.6);
  const lines = wrapLines(ctx, text, maxW);
  const lh = fs * 1.35;
  const w = Math.min(maxW, Math.max(...lines.map((l) => ctx.measureText(l).width))) + fs;
  const h = lines.length * lh + fs * 0.7;
  let bx = Math.round(x - w / 2);
  bx = clamp(bx, 4, ctx.canvas.width - w - 4);
  let by = Math.round(yBottom - h - 6 * S);
  by = Math.max(2, by);

  const px = Math.max(2, Math.round(S * 0.7));      // 픽셀 테두리 두께
  ctx.fillStyle = STATUS_COLORS.bubbleInk;
  ctx.fillRect(bx - px, by - px, w + px * 2, h + px * 2);
  ctx.fillStyle = STATUS_COLORS.bubblePaper;
  ctx.fillRect(bx, by, w, h);
  // 꼬리 (계단식 = 도트 느낌)
  const tipX = clamp(Math.round(x), bx + 6, bx + w - 12);
  for (let k = 0; k < 4; k++) {
    ctx.fillStyle = STATUS_COLORS.bubbleInk;
    ctx.fillRect(tipX - (4 - k) * px, by + h + k * px, (4 - k) * 2 * px, px);
    ctx.fillStyle = STATUS_COLORS.bubblePaper;
    ctx.fillRect(tipX - (4 - k) * px + px, by + h + k * px - 1, ((4 - k) * 2 - 2) * px, px);
  }
  ctx.fillStyle = STATUS_COLORS.bubbleText;
  ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  lines.forEach((l, i) => ctx.fillText(l, bx + fs / 2, by + fs * 0.35 + i * lh));
}

function wrapLines(ctx, text, maxW) {
  const out = [];
  let cur = '';
  for (const ch of String(text)) {
    if (ch === '\n') { out.push(cur); cur = ''; continue; }
    const test = cur + ch;
    if (ctx.measureText(test).width > maxW - 8 && cur) { out.push(cur); cur = ch; }
    else cur = test;
  }
  if (cur) out.push(cur);
  return out.slice(0, 4);
}

function wrapText(ctx, text, cx, y, maxW, lh, maxLines) {
  const lines = wrapLines(ctx, text, maxW).slice(0, maxLines);
  lines.forEach((l, i) => ctx.fillText(l, cx, y + i * lh));
}

/* ══════════════════════════ 5. UI ══════════════════════════ */

const UI = {
  /* ── 셋업 ── */
  async initSetup() {
    try {
      const [classrooms, lessons] = await Promise.all([Api.classrooms(), Api.lessons()]);
      const c = $('#sel-classroom'), l = $('#sel-lesson');
      c.innerHTML = classrooms.map((x) =>
        `<option value="${esc(x.path)}">${esc(x.class_name)} — ${esc(x.grade)} (${x.count}명)</option>`).join('');
      l.innerHTML = lessons.map((x) =>
        `<option value="${esc(x.path)}">${esc(x.title)}</option>`).join('');
      if (!classrooms.length) UI.setupError('personas/ 에 학급 JSON이 없습니다.');
      if (!lessons.length) UI.setupError('lessons/ 에 수업안 마크다운이 없습니다.');
    } catch (e) {
      UI.setupError('목록을 불러오지 못했습니다: ' + e.message);
    }
    $('#sel-backend').addEventListener('change', UI.updateBackendNote);
    UI.updateBackendNote();
  },

  /** 선택한 백엔드가 무엇을 뜻하는지 셋업 화면에서 바로 설명한다 */
  updateBackendNote() {
    const notes = {
      mock: '연습 모드 — 학생 반응이 규칙 기반이라 단순합니다. 준비 없이 화면·명령을 익히기에 좋아요.',
      codex: 'ChatGPT 구독으로 실제 AI 반응을 생성합니다. 서버 PC에서 codex login이 되어 있어야 하고, 턴당 수십 초 걸릴 수 있어요.',
      anthropic: 'Claude API로 실제 AI 반응을 생성합니다. ANTHROPIC_API_KEY가 필요하며 사용량만큼 과금됩니다.',
    };
    $('#backend-note').textContent = notes[$('#sel-backend').value] || '';
  },

  setupError(msg) {
    const el = $('#setup-error');
    el.textContent = msg;
    el.hidden = !msg;
  },

  /** 첫 수업 1회만 보여주는 3줄 길잡이 */
  firstRunIntro() {
    try {
      if (localStorage.getItem('cs_intro_done')) return;
      localStorage.setItem('cs_intro_done', '1');
    } catch (e) { return; }
    UI.addLine('system', '처음이신가요?', [
      '① 아래 입력창에 수업할 말을 그대로 적고 Enter — 학생들이 듣고 반응합니다.',
      '② 무대의 학생을 클릭하면 상세 카드가 열리고, 카드의 [지목] 버튼으로 바로 물어볼 수 있어요.',
      '③ 명령이 궁금하면 [도움말] 버튼을, 수업을 마치면 /종료 를 입력해 사후 리포트를 받으세요.',
    ].join('\n'));
  },

  /** 진행 중 세션 기억 (새로고침 복구용) */
  remember() {
    try {
      localStorage.setItem('cs_session', JSON.stringify({
        id: App.sessionId, cls: App.className, lesson: App.lessonTitle,
        backend: App.backend, t: Date.now(),
      }));
    } catch (e) { /* 프라이빗 모드 등 — 복구 기능만 포기 */ }
  },
  forget() { try { localStorage.removeItem('cs_session'); } catch (e) { /* 무시 */ } },

  /** 저장된 세션이 서버에 살아있으면 이어하기 배너를 보여준다 */
  async offerResume() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem('cs_session') || 'null'); } catch (e) { saved = null; }
    if (!saved || !saved.id || Date.now() - (saved.t || 0) > 3 * 3600 * 1000) return;
    let snap;
    try { snap = await Api.state(saved.id); } catch (e) { UI.forget(); return; }
    if (snap.ended) { UI.forget(); return; }
    $('#resume-info').textContent =
      `${snap.class_name || saved.cls} · ${snap.lesson_title || saved.lesson} (${snap.minute}분 진행)`;
    $('#resume-banner').hidden = false;
    $('#btn-resume').onclick = () => UI.resume(saved.id, snap);
    $('#btn-discard').onclick = () => { UI.forget(); $('#resume-banner').hidden = true; };
  },

  /** 서버 상태 + 전사를 다시 불러와 무대를 복원한다 */
  async resume(sessionId, snap) {
    const btn = $('#btn-resume');
    btn.disabled = true; btn.textContent = '교실을 복원하는 중...';
    try {
      App.sessionId = sessionId;
      App.className = snap.class_name || '';
      App.lessonTitle = snap.lesson_title || '';
      App.backend = snap.backend || 'mock';
      App.students = snap.students || [];
      App.seatOf = {};
      App.students.forEach((s, i) => { App.seatOf[s.id] = i; });
      App.personas = {};
      (snap.personas || []).forEach((p) => { App.personas[p.id] = p; });
      App.states = {};
      App.students.forEach((s) => { App.states[s.id] = pickState(s); });
      App.turn = snap.turn || 0; App.minute = snap.minute || 0;
      App.phase = snap.phase || '도입'; App.ended = !!snap.ended;

      await Assets.loadAll(App.students.length);
      document.body.dataset.screen = 'stage';
      $('#tb-class').textContent = App.className;
      $('#tb-lesson').textContent = App.lessonTitle;
      $('#tb-backend').textContent = App.backend;
      Stage.init();
      UI.refreshTop();

      // 전사 재생: 로그 복원 + 판서·모둠 상태 재구성 (최근 120줄)
      try {
        const t = await Api.transcript(sessionId);
        (t || []).slice(-120).forEach(UI.renderEntry);
      } catch (e) { /* 전사 복원 실패해도 수업은 계속 */ }
      UI.addSystemLine(`수업을 이어서 진행합니다 — ${App.minute}분 경과, ${App.turn}턴째`);
      UI.remember();
      if (!isMobile()) $('#teacher-input').focus();
    } catch (e) {
      UI.setupError('수업을 복원하지 못했습니다: ' + e.message);
      btn.disabled = false; btn.textContent = '이어하기';
    }
  },

  async start() {
    UI.setupError('');
    const btn = $('#btn-start');
    btn.disabled = true; btn.textContent = '교실을 준비하는 중...';
    try {
      const data = await Api.createSession({
        classroom_path: $('#sel-classroom').value,
        lesson_path: $('#sel-lesson').value,
        backend: $('#sel-backend').value,
      });
      App.sessionId = data.session_id;
      App.className = data.class_name || '';
      App.lessonTitle = data.lesson_title || '';
      App.backend = data.backend || $('#sel-backend').value;
      App.students = data.students || [];
      App.seatOf = {};
      App.students.forEach((s, i) => { App.seatOf[s.id] = i; });
      App.personas = {};
      (data.personas || []).forEach((p) => { App.personas[p.id] = p; });
      App.states = {};
      App.students.forEach((s) => { App.states[s.id] = pickState(s); });
      App.turn = data.turn || 0; App.minute = data.minute || 0;
      App.phase = data.phase || '도입'; App.ended = !!data.ended;

      await Assets.loadAll(App.students.length);
      document.body.dataset.screen = 'stage';
      $('#tb-class').textContent = App.className;
      $('#tb-lesson').textContent = App.lessonTitle;
      $('#tb-backend').textContent = App.backend;
      Stage.init();
      UI.refreshTop();
      UI.addSystemLine(`수업을 시작합니다 — ${App.className} · ${App.lessonTitle}`);
      UI.addSystemLine('입력 예)  여러분, 오늘은 비에 대해 배웁니다.   /  @윤지우 기준량이 뭘까?   /  /판서 3 : 5');
      if (App.backend === 'mock') {
        UI.addSystemLine('※ 지금은 연습 모드(mock)라 학생 반응이 규칙 기반으로 단순합니다. 실제 AI 반응을 보려면 새 수업에서 codex 또는 anthropic 백엔드를 선택하세요.');
      }
      UI.firstRunIntro();
      UI.remember();
      // 모바일에서는 시작하자마자 키보드가 올라와 무대를 가리므로 포커스하지 않는다
      if (!isMobile()) $('#teacher-input').focus();
    } catch (e) {
      UI.setupError('수업을 시작하지 못했습니다.\n' + e.message);
    } finally {
      btn.disabled = false; btn.textContent = '수업 시작';
    }
  },

  /* ── 상단 바 ── */
  refreshTop() {
    $('#tb-minute').textContent = App.minute;
    $('#tb-phase').textContent = App.phase;
    $('#tb-turn').textContent = App.turn;
    const ids = Object.keys(App.states);
    const avg = (k) => ids.length
      ? Math.round(ids.reduce((a, id) => a + (App.states[id][k] || 0), 0) / ids.length) : 0;
    const c = avg('comprehension'), i = avg('interest'), f = avg('focus');
    $('#avg-comp').textContent = c; $('#avg-comp-bar').style.width = c + '%';
    $('#avg-int').textContent = i; $('#avg-int-bar').style.width = i + '%';
    $('#avg-foc').textContent = f; $('#avg-foc-bar').style.width = f + '%';
  },

  /* ── 전사 로그 ── */
  addLine(cls, who, text) {
    const box = $('#transcript');
    const div = document.createElement('div');
    div.className = 'line ' + cls + (String(text).indexOf('\n') >= 0 ? ' pre' : '');
    div.innerHTML = (who ? `<span class="who">${esc(who)}</span>` : '') + esc(text);
    box.appendChild(div);
    UI.trimTranscript(box);
    UI.scheduleScroll(box);
  },
  addSystemLine(text) { UI.addLine('system', '', text); },
  addTurnMark() {
    const box = $('#transcript');
    const div = document.createElement('div');
    div.className = 'line turnmark';
    div.textContent = `— ${App.turn}턴 · ${App.minute}분 · ${App.phase} —`;
    box.appendChild(div);
    UI.trimTranscript(box);
    UI.scheduleScroll(box);
  },

  /** 긴 수업에서 DOM이 무한히 늘지 않도록 오래된 줄부터 접는다 (전체 기록은 서버 보관) */
  trimTranscript(box) {
    let over = box.childElementCount - TRANSCRIPT_MAX;
    if (over <= 0) return;
    if (!box.firstElementChild.classList.contains('trim-note')) {
      const n = document.createElement('div');
      n.className = 'line system trim-note';
      n.textContent = '⋯ 오래된 기록은 화면에서 접었습니다 (종료 리포트·전사 JSON에는 전부 포함됩니다)';
      box.insertBefore(n, box.firstElementChild);
      over += 1;
    }
    while (over-- > 0 && box.children.length > 1) box.children[1].remove();
  },

  /** 여러 줄이 한꺼번에 추가돼도 스크롤(강제 리플로우)은 프레임당 1회만 */
  scheduleScroll(box) {
    if (UI._scrollPending) return;
    UI._scrollPending = true;
    requestAnimationFrame(() => {
      UI._scrollPending = false;
      box.scrollTop = box.scrollHeight;
    });
  },

  nameOf(actor) {
    const s = App.students.find((x) => x.id === actor);
    return s ? s.name : actor;
  },

  /** 서버 전사 엔트리 1건을 로그에 재생 (이어하기·재동기화 공용) */
  renderEntry(e) {
    const kind = e.kind || '', content = e.content || '';
    if (kind.startsWith('teacher')) {
      UI.addLine('teacher', '교사', content);
      const m = content.match(/^(?:판서|칠판에\s*적는다)\s*[:：\-—–]\s*([\s\S]+)/);
      if (m) App.boardText = m[1].trim();
    } else if (kind.startsWith('student')) {
      UI.addLine('student', UI.nameOf(e.actor), content);
    } else if (kind === 'narration') {
      UI.addLine('narration', '무대', content);
    }
    parseGroups(content);
  },

  /** 타임아웃·409 뒤 서버와 상태를 다시 맞춘다.
      서버가 그 사이 입력을 처리했으면 놓친 전사를 재생하고, 아니면 입력을 되돌려 준다. */
  async resyncState(pendingText, input) {
    try {
      const before = App.turn;
      const snap = await Api.state(App.sessionId);
      App.turn = snap.turn || App.turn;
      App.minute = snap.minute !== undefined ? snap.minute : App.minute;
      App.phase = snap.phase || App.phase;
      App.ended = !!snap.ended;
      (snap.students || []).forEach((s) => { App.states[s.id] = pickState(s); });
      Stage.dirty = true;
      UI.refreshTop();
      if (App.turn > before) {
        try {
          const t = await Api.transcript(App.sessionId);
          (t || []).filter((e) => (e.turn || 0) > before).forEach(UI.renderEntry);
        } catch (e2) { /* 전사 없이도 게이지는 맞춰졌다 */ }
        UI.addSystemLine(`알고 보니 서버가 입력을 처리해 두었어요 — 상태를 ${App.turn}턴으로 맞췄습니다.`);
      } else {
        UI.addSystemLine('서버에 반영되지 않은 입력입니다. 아래에 남겨 두었으니 다시 보내 주세요.');
        if (input && !input.value && pendingText) input.value = pendingText;
      }
      if (App.ended) await UI.showReport(null);
    } catch (e2) {
      UI.addSystemLine('상태를 다시 맞추지 못했습니다: ' + e2.message);
      if (input && !input.value && pendingText) input.value = pendingText;
    }
  },

  /* ── 명령 도움말 (서버 왕복 없이 즉시 표시) ── */
  showHelp() {
    UI.addLine('system', '도움말', [
      '일반 텍스트          전체 발화 (학생들이 듣고 반응)',
      '@이름 질문           특정 학생 지목  예) @윤지우 기준량이 뭘까?',
      '/판서 내용           칠판에 적기     예) /판서 3 : 5',
      '/활동 지시문         개별 활동 시작',
      '/모둠 4인            모둠 자동 편성  (또는 /모둠 S01,S04/S02,S05)',
      '/모둠활동 지시문     모둠 활동 시작',
      '/순회 이름 [말]      순회 지도',
      '/칭찬 이름 [말]      칭찬  ·  /주의 이름 [말]  주의 주기',
      '/시간 10분           수업 시간 건너뛰기',
      '/돌발 [카드명]       돌발 상황 발생 (비우면 무작위)',
      '/상태                전체 학생 상태표',
      '/종료                수업 종료 + 사후 리포트',
    ].join('\n'));
  },

  /** 서버 _resolve와 같은 규칙: ID → 이름 완전일치 → 이름 앞부분 일치 */
  resolveLocal(token) {
    const key = (token || '').trim().replace(/,+$/, '');
    if (!key) return null;
    const up = key.toUpperCase();
    let hit = App.students.find((s) => s.id.toUpperCase() === up);
    if (!hit) hit = App.students.find((s) => s.name === key);
    if (!hit) hit = App.students.find((s) => s.name.startsWith(key) || key.startsWith(s.name));
    return hit || null;
  },

  /** 서버로 보내기 전에 오타를 잡는다. 문제가 있으면 안내를 출력하고 false */
  precheck(text) {
    if (text.startsWith('@')) {
      const head = text.slice(1).split(/\s+/)[0];
      if (!UI.resolveLocal(head)) {
        const names = App.students.map((s) => s.name).join(', ');
        UI.addLine('system', '무대', `'${head}' 학생을 찾을 수 없습니다.\n우리 반: ${names}`);
        return false;
      }
      return true;
    }
    if (text.startsWith('/')) {
      const cmd = text.slice(1).split(/\s+/)[0];
      const known = ['판서', '활동', '모둠', '모둠활동', '순회', '칭찬', '주의',
                     '시간', '돌발', '상태', '종료', '도움말'];
      if (!known.includes(cmd)) {
        UI.addLine('system', '무대', `알 수 없는 명령입니다: /${cmd}\n[도움말] 버튼을 누르면 명령 목록이 나옵니다.`);
        return false;
      }
      if (['순회', '칭찬', '주의'].includes(cmd)) {
        const name = (text.slice(1).split(/\s+/)[1] || '');
        if (name && !UI.resolveLocal(name)) {
          UI.addLine('system', '무대', `'${name}' 학생을 찾을 수 없습니다. 학생을 클릭한 뒤 버튼을 쓰면 이름이 자동으로 들어갑니다.`);
          return false;
        }
      }
    }
    return true;
  },

  /* ── 턴 전송 ── */
  async send(rawText) {
    const input = $('#teacher-input');
    const text = (rawText !== undefined ? rawText : input.value).trim();
    if (!text || App.busy || App.ended) return;
    Autocomplete.close();
    // 도움말은 서버 왕복 없이 즉시 (LLM 호출·대기 없음)
    if (/^\/(도움말|help|\?)(\s|$)/.test(text)) { UI.showHelp(); input.value = ''; return; }
    // 오타(없는 명령·없는 학생)는 보내기 전에 잡는다 — 입력은 지우지 않고 남겨 둔다
    if (!UI.precheck(text)) return;
    // 실수 방지: 종료는 한 번 더 확인 (리포트 생성 후에는 되돌릴 수 없음)
    if (/^\/종료(\s|$)/.test(text)
        && !window.confirm('수업을 종료하고 사후 리포트를 생성할까요?\n종료 후에는 수업을 이어갈 수 없습니다.')) {
      return;
    }
    input.value = '';
    UI.setBusy(true);
    try {
      const r = await Api.turn(App.sessionId, text);
      UI.applyTurn(r);
      if (r.notice) UI.addSystemLine(r.notice);
      if (r.ended) await UI.showReport(r.report_markdown, r.report_saved_path);
    } catch (e) {
      if (e.code === 'timeout') {
        UI.addLine('system', '오류', e.message + '  서버가 그 사이 처리를 마쳤을 수 있어 상태를 확인합니다…');
        await UI.resyncState(text, input);
      } else if (e.code === 409) {
        UI.addLine('system', '안내', e.message);
        setTimeout(() => { if (!App.busy && !App.ended) UI.resyncState(text, input); }, 5000);
      } else {
        UI.addLine('system', '오류', e.message + '  (입력한 내용은 입력창에 남겨 두었어요)');
        if (!input.value) input.value = text;   // 쓰던 내용 유실 방지
      }
    } finally {
      UI.setBusy(false);
      input.focus();
    }
  },

  applyTurn(r) {
    Stage.dirty = true;   // 게이지·감정·판서가 바뀌므로 다음 프레임에 반드시 그린다
    App.turn = r.turn !== undefined ? r.turn : App.turn + 1;
    App.minute = r.minute !== undefined ? r.minute : App.minute;
    App.phase = r.phase || App.phase;
    App.ended = !!r.ended;
    if (r.states) {
      Object.keys(r.states).forEach((id) => { App.states[id] = Object.assign({}, App.states[id], r.states[id]); });
    }
    UI.addTurnMark();
    (r.events || []).forEach((ev) => {
      const kind = ev.kind || '';
      const content = ev.content || '';
      if (kind.startsWith('teacher')) {
        UI.addLine('teacher', '교사', content);
        // 판서 내용을 칠판에 남긴다 ("판서: …" / "칠판에 적는다 — …" 두 형식 지원)
        const m = content.match(/^(?:판서|칠판에\s*적는다)\s*[:：\-—–]\s*([\s\S]+)/);
        if (m) App.boardText = m[1].trim();
      } else if (kind.startsWith('student')) {
        const name = UI.nameOf(ev.actor);
        UI.addLine('student', name, content);
        if (kind === 'student_say' && App.seatOf[ev.actor] !== undefined) {
          App.bubbles.push({ sid: ev.actor, text: content, t0: performance.now() });
        }
      } else if (kind === 'narration') {
        UI.addLine('narration', '무대', content);
      } else {
        UI.addLine('system', '무대', content);
      }
      parseGroups(content);
    });
    UI.refreshTop();
    if (App.selected) UI.renderDetail(App.selected);
  },

  setBusy(on) {
    App.busy = on;
    $('#busy').hidden = !on;
    $('#btn-send').disabled = on;
    $('#teacher-input').disabled = on;
    clearInterval(UI._busyTimer);
    if (on) {
      const t0 = Date.now();
      const label = $('#busy');
      const slow = App.backend !== 'mock';
      const base = slow ? '학생들이 반응하는 중... (AI 백엔드는 턴당 수십 초 걸릴 수 있어요)' : '학생들이 반응하는 중...';
      label.innerHTML = '<span class="dots"></span>' + base;
      UI._busyTimer = setInterval(() => {
        const sec = Math.floor((Date.now() - t0) / 1000);
        if (sec >= 3) label.innerHTML = `<span class="dots"></span>${base} ${sec}초`;
      }, 1000);
    }
  },
  _busyTimer: 0,

  /* ── 학생 상세 카드 ── */
  /** 모바일 바텀시트 열기/닫기 (데스크톱에서는 CSS상 아무 영향 없음) */
  setSheet(open) {
    document.body.classList.toggle('sheet-open', !!open);
  },

  selectStudent(id) {
    App.selected = id;
    Stage.dirty = true;
    // 스크린리더 안내 (시각적 표시는 캔버스라 읽히지 않는다)
    const live = $('#sr-live');
    if (live) {
      if (id) {
        const stu = App.students.find((s) => s.id === id);
        const st = App.states[id] || {};
        live.textContent = stu
          ? `${stu.name} 선택됨. 이해 ${st.comprehension ?? '-'}, 흥미 ${st.interest ?? '-'}, 집중 ${st.focus ?? '-'}, 감정 ${st.emotion || '평온'}.`
          : '';
      } else {
        live.textContent = '선택 해제됨.';
      }
    }
    if (!id) {
      $('#detail-card').hidden = true;
      $('#detail-empty').hidden = false;
      UI.setSheet(false);
      return;
    }
    $('#detail-empty').hidden = true;
    $('#detail-card').hidden = false;
    UI.renderDetail(id);
    UI.setSheet(true);
    if (isMobile()) $('#side-panel').scrollTop = 0;
  },

  /** 상세 카드 '오늘 발언' — 펼칠 때 그 학생의 발화·행동만 모아 보여준다 */
  async loadHistory(id) {
    const body = $('#dc-history-body');
    // 같은 턴에 같은 학생이면 캐시 재사용 (턴이 지나면 새로 불러옴)
    if (UI._histFor === id && UI._histTurn === App.turn) return;
    UI._histFor = id; UI._histTurn = App.turn;
    body.innerHTML = '<p class="dim">여는 중...</p>';
    try {
      const t = await Api.transcript(App.sessionId);
      const mine = (t || []).filter((e) => e.actor === id);
      if (!mine.length) {
        body.innerHTML = '<p class="dim">아직 발언이 없습니다. 지목(@이름)해 보세요.</p>';
        return;
      }
      body.innerHTML = mine.slice(-30).map((e) => {
        const text = e.kind === 'student_say' ? `"${esc(e.content)}"` : `(${esc(e.content)})`;
        return `<p><em>[${e.minute}분]</em> ${text}</p>`;
      }).join('');
    } catch (e) {
      body.innerHTML = `<p class="dim">불러오지 못했습니다: ${esc(e.message)}</p>`;
    }
  },

  renderDetail(id) {
    const stu = App.students.find((s) => s.id === id);
    if (!stu) return;
    // 다른 학생으로 바뀌면 발언 기록은 접고, 이전 학생 내용이 비치지 않게 본문도 비운다
    const hist = $('#dc-history');
    if (hist && UI._histFor !== id) {
      hist.open = false;
      UI._histFor = null;
      $('#dc-history-body').innerHTML = '<p class="dim">여는 중...</p>';
    }
    if (hist && hist.open) UI.loadHistory(id);
    const st = App.states[id] || {};
    const p = App.personas[id] || {};
    $('#dc-name').textContent = `${stu.name} (${stu.id})`;
    $('#dc-meta').textContent = `성취수준 ${stu.achievement_level || '—'}`
      + (App.groups[id] ? ` · ${App.groups[id]}모둠` : '');
    const set = (bar, val, num) => {
      $(bar).style.width = clamp(val || 0, 0, 100) + '%';
      $(num).textContent = val !== undefined ? val : '—';
    };
    set('#dc-comp-bar', st.comprehension, '#dc-comp');
    set('#dc-int-bar', st.interest, '#dc-int');
    set('#dc-foc-bar', st.focus, '#dc-foc');
    $('#dc-emo').textContent = EMOTION_EMOJI[Stage.emotionKey(st)] || '😐';
    $('#dc-action').textContent = `${st.emotion || '—'} · ${st.visible_action || '특별한 움직임 없음'}`;

    const rows = [
      ['사전 지식', p.prior_knowledge],
      ['학습 스타일', p.learning_style],
      ['흥미/관심사', (p.interests || []).join(', ')],
      ['성격', p.personality],
      ['교우 관계', p.social],
      ['교사 메모', p.notes],
    ].filter(([, v]) => v);
    $('#dc-persona').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');

    // 초상화 (좌석 스프라이트 첫 프레임)
    const i = App.seatOf[id] || 0;
    const sprite = Assets.character('char_s' + String(i + 1).padStart(2, '0'), i, false);
    const pc = $('#dc-portrait').getContext('2d');
    pc.imageSmoothingEnabled = true;
    pc.imageSmoothingQuality = 'high';
    pc.clearRect(0, 0, SPRITE_W * ASSET_SCALE, SPRITE_H * ASSET_SCALE);
    const sourceScale = sprite.sourceScale || 1;
    pc.drawImage(
      sprite.img,
      0,
      0,
      SPRITE_W * sourceScale,
      SPRITE_H * sourceScale,
      0,
      0,
      SPRITE_W * ASSET_SCALE,
      SPRITE_H * ASSET_SCALE,
    );
  },

  /* ── 종료 리포트 ── */
  async showReport(md, savedPath) {
    let report = md;
    if (!report) {
      try {
        const r = await Api.end(App.sessionId);
        report = r.report_markdown;
        savedPath = savedPath || r.report_saved_path;
      } catch (e) { report = null; }
    }
    App.reportMd = report || '# 수업 종료\n\n리포트를 생성하지 못했습니다.';
    let html = mdToHtml(App.reportMd);
    if (savedPath) {
      html += `<p class="saved-note">💾 서버에도 저장됨: <code>${esc(savedPath)}</code> (전사 JSON 포함)</p>`;
    }
    $('#report-body').innerHTML = html;
    document.body.dataset.screen = 'report';
    UI.forget();
  },
};

/** 스냅샷의 학생 항목에서 상태 필드만 추출 */
function pickState(s) {
  return {
    comprehension: s.comprehension, interest: s.interest, focus: s.focus,
    emotion: s.emotion, visible_action: s.visible_action,
  };
}

/** 모둠 편성 안내 텍스트에서 모둠 정보를 추출 (엔진이 states에 모둠을 주지 않는 경우 대비) */
function parseGroups(text) {
  if (!text || !/모둠/.test(text)) return;
  const re = /(\d+)\s*모둠\s*[:：]\s*([^|\n]+)/g;
  let m, found = {};
  while ((m = re.exec(text)) !== null) {
    const gi = parseInt(m[1], 10);
    const seg = m[2];
    const ids = seg.match(/S\d{2}/gi) || [];
    ids.forEach((id) => { found[id.toUpperCase()] = gi; });
    if (!ids.length) {
      App.students.forEach((s) => { if (seg.indexOf(s.name) >= 0) found[s.id] = gi; });
    }
  }
  if (!Object.keys(found).length) {
    // "모둠을 편성한다 — 김하늘·이준서 / 정수아·강도윤" 형식 (구분자: / 와 ·,·, )
    const tail = text.split(/[—–\-:：]/).slice(1).join(' ');
    const segs = tail.split('/').map((x) => x.trim()).filter(Boolean);
    if (segs.length >= 2) {
      segs.forEach((seg, gi) => {
        (seg.match(/S\d{2}/gi) || []).forEach((id) => { found[id.toUpperCase()] = gi + 1; });
        App.students.forEach((s) => { if (seg.indexOf(s.name) >= 0) found[s.id] = gi + 1; });
      });
    }
  }
  if (Object.keys(found).length) App.groups = found;
}

/* ══════════════════════════ 6. 미니 마크다운 렌더러 ══════════════════════════
   외부 라이브러리 금지 → 리포트에 필요한 최소 문법만 직접 변환한다.
   지원: #~#### 제목, 목록(-,*,1.), 표, 인용(>), 수평선, 코드블록,
         인라인 **굵게** *기울임* `코드` [링크](url)
   ============================================================== */

function esc(s) {
  return String(s === undefined || s === null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function inlineMd(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

function mdToHtml(md) {
  const lines = String(md || '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let i = 0, inCode = false, listType = null, para = [];

  const flushPara = () => {
    if (para.length) { out.push('<p>' + para.map(inlineMd).join('<br>') + '</p>'); para = []; }
  };
  const closeList = () => { if (listType) { out.push(`</${listType}>`); listType = null; } };

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {                       // 코드 블록
      flushPara(); closeList();
      if (!inCode) { out.push('<pre><code>'); inCode = true; }
      else { out.push('</code></pre>'); inCode = false; }
      i++; continue;
    }
    if (inCode) { out.push(esc(line) + '\n'); i++; continue; }

    if (!line.trim()) { flushPara(); closeList(); i++; continue; }

    const h = line.match(/^(#{1,4})\s+(.*)$/);         // 제목
    if (h) {
      flushPara(); closeList();
      out.push(`<h${h[1].length}>${inlineMd(h[2])}</h${h[1].length}>`);
      i++; continue;
    }
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {   // 수평선
      flushPara(); closeList(); out.push('<hr>'); i++; continue;
    }
    if (/^\s*>/.test(line)) {                          // 인용
      flushPara(); closeList();
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++; }
      out.push('<blockquote>' + buf.map(inlineMd).join('<br>') + '</blockquote>');
      continue;
    }
    if (/^\s*\|/.test(line)) {                         // 표
      flushPara(); closeList();
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(lines[i]); i++; }
      out.push(renderTable(rows));
      continue;
    }
    const li = line.match(/^\s*([-*+]|\d+[.)])\s+(.*)$/); // 목록
    if (li) {
      flushPara();
      const type = /^\d/.test(li[1]) ? 'ol' : 'ul';
      if (listType !== type) { closeList(); out.push(`<${type}>`); listType = type; }
      out.push('<li>' + inlineMd(li[2]) + '</li>');
      i++; continue;
    }
    closeList();
    para.push(line.trim());
    i++;
  }
  flushPara(); closeList();
  if (inCode) out.push('</code></pre>');
  return out.join('\n');
}

function renderTable(rows) {
  const cells = (r) => r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
  let head = null, body = [];
  rows.forEach((r, idx) => {
    const c = cells(r);
    if (idx === 1 && c.every((x) => /^:?-{2,}:?$/.test(x))) return;  // 구분선
    if (idx === 0) head = c; else body.push(c);
  });
  const th = head ? '<thead><tr>' + head.map((c) => `<th>${inlineMd(c)}</th>`).join('') + '</tr></thead>' : '';
  const tb = '<tbody>' + body.map((r) => '<tr>' + r.map((c) => `<td>${inlineMd(c)}</td>`).join('') + '</tr>').join('') + '</tbody>';
  return `<table>${th}${tb}</table>`;
}

/* ══════════════════════════ 7. 이벤트 바인딩 ══════════════════════════ */

/* ── @학생 자동완성 ── */
const Autocomplete = {
  open: false, idx: -1, items: [], prefix: '',

  /** 입력값이 '@…' 또는 '/순회|칭찬|주의 …'로 이름을 고르는 중이면 후보를 띄운다 */
  update() {
    const input = $('#teacher-input');
    const m = input.value.match(/^(@|\/(?:순회|칭찬|주의)\s+)(\S*)$/);
    if (!m || App.ended || !App.students.length) return Autocomplete.close();
    const q = m[2];
    const qUp = q.toUpperCase();
    const items = App.students.filter((s) =>
      !q || s.name.includes(q) || s.id.toUpperCase().startsWith(qUp));
    if (!items.length) return Autocomplete.close();
    Autocomplete.items = items;
    Autocomplete.prefix = m[1];
    Autocomplete.idx = -1;
    Autocomplete.open = true;
    const box = $('#autocomplete');
    box.innerHTML = '';
    items.forEach((s, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'ac-item';
      b.textContent = s.name;
      // 포커스를 뺏지 않도록 mousedown에서 처리 (click은 blur 이후라 입력이 흐트러진다)
      b.addEventListener('mousedown', (e) => { e.preventDefault(); Autocomplete.pick(i); });
      box.appendChild(b);
    });
    box.hidden = false;
  },

  move(delta) {
    if (!Autocomplete.open) return;
    const n = Autocomplete.items.length;
    Autocomplete.idx = (Autocomplete.idx + delta + n) % n;
    $('#autocomplete').querySelectorAll('.ac-item').forEach((el, i) => {
      el.classList.toggle('active', i === Autocomplete.idx);
    });
  },

  pick(i) {
    const s = Autocomplete.items[i];
    if (!s) return;
    const input = $('#teacher-input');
    input.value = Autocomplete.prefix + s.name + ' ';
    Autocomplete.close();
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  },

  close() {
    Autocomplete.open = false;
    Autocomplete.idx = -1;
    $('#autocomplete').hidden = true;
  },
};

function insertCommand(cmd) {
  const input = $('#teacher-input');
  let text = cmd;
  if (cmd === 'help') { UI.showHelp(); return; }
  if (cmd === 'incident') {
    const card = $('#incident-card').value;
    text = card ? `/돌발 ${card}` : '/돌발';
  } else if ((cmd === '@' || cmd === '/순회 ' || cmd === '/칭찬 ' || cmd === '/주의 ') && App.selected) {
    const stu = App.students.find((s) => s.id === App.selected);
    if (stu) text = cmd + stu.name + ' ';
  }
  // 즉시 실행형 명령(인자 불필요)은 그대로 두고, 나머지는 커서를 끝에 둔다
  input.value = text;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

/** 사람이 알아볼 수 있는 다운로드 파일명 — "리포트_6학년3반_2026-08-15.md" */
function exportName(prefix, ext) {
  const cls = (App.className || '수업').replace(/[\\/:*?"<>|\s]+/g, '');
  const d = new Date();
  const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return `${prefix}_${cls}_${ymd}.${ext}`;
}

function download(filename, content, type) {
  const blob = new Blob([content], { type: type || 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

document.addEventListener('DOMContentLoaded', () => {
  UI.initSetup();
  UI.offerResume();

  // 네트워크 단절을 즉시 알린다 (전송 실패 후에야 아는 것보다 빠르게)
  window.addEventListener('offline', () => {
    if (document.body.dataset.screen === 'stage') UI.addSystemLine('📴 인터넷 연결이 끊어졌습니다. 연결이 돌아오면 이어서 진행할 수 있어요.');
  });
  window.addEventListener('online', () => {
    if (document.body.dataset.screen === 'stage') UI.addSystemLine('✅ 연결이 복구되었습니다.');
  });
  $('#btn-start').addEventListener('click', UI.start);

  $('#btn-send').addEventListener('click', () => UI.send());
  $('#teacher-input').addEventListener('input', () => Autocomplete.update());
  $('#teacher-input').addEventListener('blur', () => setTimeout(Autocomplete.close, 150));
  $('#teacher-input').addEventListener('keydown', (e) => {
    if (Autocomplete.open) {
      if (e.key === 'ArrowDown') { e.preventDefault(); Autocomplete.move(1); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); Autocomplete.move(-1); return; }
      if (e.key === 'Escape') { Autocomplete.close(); return; }
      if (e.key === 'Enter' && !e.isComposing && Autocomplete.idx >= 0) {
        e.preventDefault(); Autocomplete.pick(Autocomplete.idx); return;
      }
    }
    if (e.key === 'Enter' && !e.isComposing) UI.send();
  });

  document.querySelectorAll('#cmd-bar button, .dc-actions button').forEach((b) => {
    b.addEventListener('click', () => {
      insertCommand(b.dataset.cmd);
      // 모바일: 바텀시트에서 명령을 고르면 시트를 닫아 입력줄을 보여준다 (선택 표시는 유지)
      if (isMobile() && b.closest('.dc-actions')) UI.setSheet(false);
    });
  });
  $('#dc-close').addEventListener('click', () => UI.selectStudent(null));
  $('#dc-history').addEventListener('toggle', () => {
    if ($('#dc-history').open && App.selected) UI.loadHistory(App.selected);
  });
  $('#sheet-backdrop').addEventListener('click', () => UI.selectStudent(null));

  // 전사 로그 접기/펴기 (모바일 전용 버튼)
  $('#tr-toggle').addEventListener('click', () => {
    const on = document.body.classList.toggle('tr-expanded');
    const btn = $('#tr-toggle');
    btn.textContent = on ? '▼' : '▲';
    btn.setAttribute('aria-expanded', on ? 'true' : 'false');
    const box = $('#transcript');
    box.scrollTop = box.scrollHeight;
    // 펴면 화면이 길어지므로 입력줄이 보이도록 무대 화면을 아래로 붙인다
    const sc = $('#screen-stage');
    if (on) requestAnimationFrame(() => { sc.scrollTop = sc.scrollHeight; });
  });

  $('#btn-download').addEventListener('click', async () => {
    try {
      const t = await Api.transcript(App.sessionId);
      download(exportName('전사', 'json'), JSON.stringify(t, null, 2));
    } catch (e) {
      alert('전사를 내려받지 못했습니다: ' + e.message);
    }
  });
  $('#btn-download-md').addEventListener('click', () => {
    download(exportName('리포트', 'md'), App.reportMd, 'text/markdown;charset=utf-8');
  });
  $('#btn-print').addEventListener('click', () => { window.print(); });
  $('#btn-restart').addEventListener('click', () => { location.reload(); });
});
