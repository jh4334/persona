/* ============================================================
   보이는 교실 — 프론트엔드 (바닐라 JS, 외부 라이브러리·CDN 없음)

   구성
     1) API 래퍼        : 턴 단위 fetch (웹소켓 불필요)
     2) 에셋 로더        : /static/assets/ 의 PNG를 시도하고, 없으면 코드로 그린
                          픽셀 폴백 스프라이트를 사용 (콘솔 경고 없음)
     3) 캔버스 무대      : 336×256 논리 캔버스를 정수 배율로 확대 (image-rendering: pixelated)
     4) UI 바인딩        : 셋업 / 무대 / 종료 리포트 3화면
     5) 미니 마크다운 렌더러 (리포트용, 외부 라이브러리 금지라 직접 구현)
   ============================================================ */
'use strict';

/* ══════════════════════════ 0. 설정 ══════════════════════════ */

const COLS = 4;                       // 책상 열 수
const LOGICAL_W = 336;                // 논리 캔버스 가로 (픽셀아트 원본 해상도)
const DESK_W = 44, DESK_H = 14;
const COL_X = [48, 128, 208, 288];    // 각 열의 중심 x
const ROW_Y0 = 110, ROW_GAP = 54;     // 첫 줄 책상 윗변 y, 줄 간격
const SPRITE_W = 32, SPRITE_H = 48;
const WALL_H = 46;                    // 앞쪽 벽 높이

const ASSET_BASE = '/static/assets/';
const BUBBLE_MS = 6000;               // 말풍선 유지 시간
const CANVAS_FONT = '"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif';

// 감정 → 이모지 (에셋 emotes.png가 있으면 시트 인덱스를 우선 사용)
const EMOTION_ORDER = ['평온', '들뜸', '위축', '불안', '지루함', '몰입', '졸림', '손듦'];
const EMOTION_EMOJI = {
  '평온': '😌', '들뜸': '✨', '위축': '😟', '불안': '😰', '지루함': '🥱',
  '몰입': '🤩', '졸림': '😴', '손듦': '🙋', '피곤': '😴', '흥분': '✨',
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

/* ══════════════════════════ 2. API ══════════════════════════ */

async function api(path, options) {
  const res = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, options));
  if (!res.ok) {
    let detail = res.status + ' ' + res.statusText;
    try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (e) { /* 무시 */ }
    throw new Error(detail);
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
      sprite = { img: png, frames: Math.max(1, Math.round(png.width / SPRITE_W)), fallback: false };
    } else {
      sprite = { img: buildFallbackSheet(paletteIndex, isTeacher), frames: 3, fallback: true };
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
    ? { hair: '#20242e', shirt: '#5b6b8c', pants: '#2b303d' }
    : PALETTES[paletteIndex % PALETTES.length];
  const skin = SKIN[paletteIndex % SKIN.length];
  const ink = '#1a1420';                       // 외곽선
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
  R(10, 45, 7, 2, '#2a2a33');
  R(16, 45, 7, 2, '#2a2a33');

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
  R(14 + dx, 17 + dy, 4, 1, '#a5525a');
  // 볼 터치
  R(10 + dx, 15 + dy, 2, 1, 'rgba(230,120,120,.55)');
  R(21 + dx, 15 + dy, 2, 1, 'rgba(230,120,120,.55)');

  if (isTeacher) { // 교사 표식: 옷깃 + 손에 든 자
    R(13, 21 + dy, 6, 2, '#e8ebf5');
    R(26, 22 + dy, 2, 12, '#d9c08a');
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
    Stage.canvas.addEventListener('click', Stage.onClick);
    window.addEventListener('resize', Stage.resize);
    Stage.layout();
    Stage.resize();
    const loop = () => { Stage.draw(); Stage.rafId = requestAnimationFrame(loop); };
    Stage.rafId = requestAnimationFrame(loop);
  },

  /** 학생 수에 맞춰 논리 캔버스 높이를 정한다 (4열 기준) */
  layout() {
    const rows = Math.max(1, Math.ceil(App.students.length / COLS));
    Stage.W = LOGICAL_W;
    Stage.H = ROW_Y0 + ROW_GAP * (rows - 1) + DESK_H + 32;
    Stage.buf.width = Stage.W;
    Stage.buf.height = Stage.H;
  },

  seat(i) {
    const col = i % COLS, row = Math.floor(i / COLS);
    const cx = COL_X[col];
    const deskTop = ROW_Y0 + row * ROW_GAP;
    return { cx, deskTop, spriteX: cx - SPRITE_W / 2, spriteY: deskTop + 10 - SPRITE_H };
  },

  resize() {
    const wrap = $('#canvas-wrap');
    if (!wrap) return;
    const availW = wrap.clientWidth - 20, availH = wrap.clientHeight - 20;
    const s = Math.max(2, Math.floor(Math.min(availW / Stage.W, availH / Stage.H)));
    Stage.scale = clamp(s, 2, 6);
    Stage.canvas.width = Stage.W * Stage.scale;
    Stage.canvas.height = Stage.H * Stage.scale;
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

  /* ── 배경(교실) ── */
  drawRoom(g) {
    const W = Stage.W, H = Stage.H;
    // 나무 바닥 (타일 16px, 판자 이음선)
    g.fillStyle = '#b5824a';
    g.fillRect(0, WALL_H, W, H - WALL_H);
    for (let y = WALL_H; y < H; y += 16) {
      g.fillStyle = (Math.floor(y / 16) % 2) ? '#ad7b45' : '#b98950';
      g.fillRect(0, y, W, 16);
      g.fillStyle = '#9a6a3a';
      g.fillRect(0, y + 15, W, 1);
      for (let x = ((y / 16) % 2) * 32; x < W; x += 64) g.fillRect(x, y, 1, 15);
    }
    // 앞쪽 벽
    g.fillStyle = '#d8d0bb'; g.fillRect(0, 0, W, WALL_H);
    g.fillStyle = '#c6bda6'; g.fillRect(0, 0, W, 6);
    g.fillStyle = '#8e846d'; g.fillRect(0, WALL_H - 4, W, 4);
    g.fillStyle = '#7a7159'; g.fillRect(0, WALL_H - 1, W, 1);

    // 칠판
    if (Assets.images.blackboard) {
      g.drawImage(Assets.images.blackboard, 92, 6);
    } else {
      g.fillStyle = '#7a5a33'; g.fillRect(92, 6, 152, 34);       // 나무 틀
      g.fillStyle = '#5f4325'; g.fillRect(92, 36, 152, 4);       // 분필받이
      g.fillStyle = '#2c4a3b'; g.fillRect(95, 9, 146, 25);       // 초록 판
      g.fillStyle = 'rgba(255,255,255,.10)'; g.fillRect(95, 9, 146, 2);
      g.fillStyle = '#e8e8e0'; g.fillRect(97, 37, 6, 2); g.fillRect(105, 37, 4, 2);
    }
    // 창문
    g.fillStyle = '#e7eef5'; g.fillRect(8, 8, 40, 30);
    g.fillStyle = '#96cfee'; g.fillRect(11, 11, 34, 24);
    g.fillStyle = '#bfe4f7'; g.fillRect(11, 11, 34, 8);
    g.fillStyle = '#e7eef5'; g.fillRect(27, 11, 2, 24); g.fillRect(11, 22, 34, 2);
    g.fillStyle = '#a9b0bb'; g.fillRect(8, 38, 40, 2);
    // 게시판
    g.fillStyle = '#8a6b45'; g.fillRect(286, 6, 42, 34);
    g.fillStyle = '#c69a63'; g.fillRect(289, 9, 36, 28);
    const notes = [['#f2f0d8', 292, 12], ['#f7c6c6', 305, 12], ['#cfe3f7', 292, 24], ['#d8f0cb', 305, 24]];
    notes.forEach(([c, x, y]) => { g.fillStyle = c; g.fillRect(x, y, 11, 9); });
    // 게시판 옆 시계
    g.fillStyle = '#f0f0f0'; g.fillRect(262, 12, 12, 12);
    g.fillStyle = '#2a2a33'; g.fillRect(267, 14, 1, 5); g.fillRect(267, 18, 4, 1);

    // 교탁
    if (Assets.images.desk_teacher) {
      g.drawImage(Assets.images.desk_teacher, 148, 50);
    } else {
      g.fillStyle = '#6a4a2a'; g.fillRect(148, 50, 56, 18);
      g.fillStyle = '#c9954f'; g.fillRect(148, 50, 56, 5);
      g.fillStyle = '#4e361e'; g.fillRect(152, 68, 4, 4); g.fillRect(196, 68, 4, 4);
    }
    // 화분 (소품)
    g.fillStyle = '#8c5a3c'; g.fillRect(16, 60, 12, 9);
    g.fillStyle = '#4f9a52'; g.fillRect(18, 52, 8, 8); g.fillRect(15, 55, 4, 4); g.fillRect(25, 55, 4, 4);
    // 사물함 (우측 뒤)
    g.fillStyle = '#9aa2b5'; g.fillRect(306, 52, 24, 26);
    g.fillStyle = '#7d8598'; g.fillRect(306, 52, 24, 2); g.fillRect(318, 52, 1, 26);
    g.fillStyle = '#5c6377'; g.fillRect(312, 62, 2, 2); g.fillRect(322, 62, 2, 2);
  },

  drawDesk(g, s, sid) {
    const x = s.cx - DESK_W / 2, y = s.deskTop;
    if (Assets.images.desk_student) {
      g.drawImage(Assets.images.desk_student, x, y);
    } else {
      g.fillStyle = '#3f2c19'; g.fillRect(x - 1, y - 1, DESK_W + 2, DESK_H + 2);
      g.fillStyle = '#c9954f'; g.fillRect(x, y, DESK_W, 5);          // 상판
      g.fillStyle = '#a87a3c'; g.fillRect(x, y + 5, DESK_W, 4);      // 서랍
      g.fillStyle = '#6a4a2a'; g.fillRect(x, y + 9, DESK_W, DESK_H - 9);
      g.fillStyle = '#4e361e'; g.fillRect(x + 3, y + DESK_H, 3, 4); g.fillRect(x + DESK_W - 6, y + DESK_H, 3, 4);
      g.fillStyle = '#f2efe4'; g.fillRect(x + 6, y + 1, 12, 3);      // 책 한 권
    }
    // 모둠 테두리
    const grp = App.groups[sid];
    if (grp) {
      g.strokeStyle = GROUP_COLORS[(grp - 1) % GROUP_COLORS.length];
      g.lineWidth = 1;
      g.strokeRect(x - 2.5, y - 2.5, DESK_W + 5, DESK_H + 5);
    }
    // 선택 표시
    if (App.selected === sid) {
      g.strokeStyle = '#ffe066'; g.lineWidth = 1;
      g.strokeRect(x - 4.5, s.spriteY - 4.5, DESK_W + 9, s.deskTop + DESK_H + 4 - s.spriteY + 5);
    }
  },

  drawGauges(g, s, st) {
    const bars = [
      [st.comprehension, '#4da3ff'],
      [st.interest, '#ffd23f'],
      [st.focus, '#5fd97a'],
    ];
    const w = 26, x = s.cx - w / 2;
    let y = s.deskTop + DESK_H + 5;
    bars.forEach(([v, c]) => {
      g.fillStyle = 'rgba(20,16,10,.55)'; g.fillRect(x - 1, y - 1, w + 2, 4);
      g.fillStyle = '#2c2216'; g.fillRect(x, y, w, 2);
      g.fillStyle = c; g.fillRect(x, y, Math.round(w * clamp(v, 0, 100) / 100), 2);
      y += 4;
    });
  },

  drawCharacter(g, sprite, x, y, frame) {
    const f = Math.min(frame, sprite.frames - 1);
    g.drawImage(sprite.img, f * SPRITE_W, 0, SPRITE_W, SPRITE_H, x, y, SPRITE_W, SPRITE_H);
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

    g.imageSmoothingEnabled = false;
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
      Stage.drawCharacter(g, sprite, s.spriteX, s.spriteY, frame);
      Stage.drawDesk(g, s, stu.id);
      Stage.drawGauges(g, s, st);
    });

    // 논리 버퍼 → 화면 (정수 배율 확대, 보간 없음)
    const ctx = Stage.ctx, S = Stage.scale;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, Stage.canvas.width, Stage.canvas.height);
    ctx.drawImage(Stage.buf, 0, 0, Stage.W * S, Stage.H * S);

    Stage.drawOverlay(ctx, S, t);
  },

  /** 텍스트류(이름·말풍선·이모지·판서)는 화면 해상도로 그려야 읽을 수 있다 */
  drawOverlay(ctx, S, t) {
    // 판서 내용 (칠판 위)
    if (App.boardText) {
      ctx.save();
      ctx.beginPath(); ctx.rect(96 * S, 10 * S, 144 * S, 24 * S); ctx.clip();
      ctx.font = `${Math.round(3.4 * S)}px ${CANVAS_FONT}`;
      ctx.fillStyle = '#eef4ea'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      wrapText(ctx, App.boardText, 168 * S, 12 * S, 138 * S, 4.2 * S, 3);
      ctx.restore();
    }
    // 교사 이름표
    ctx.font = `${Math.round(3.2 * S)}px ${CANVAS_FONT}`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    ctx.fillRect(112 * S, 60 * S, 32 * S, 6 * S);
    ctx.fillStyle = '#ffe9b0';
    ctx.fillText('교사', 128 * S, 60.6 * S);

    App.students.forEach((stu, i) => {
      const s = Stage.seat(i);
      const st = App.states[stu.id] || {};
      // 이름표
      const ny = (s.deskTop + DESK_H + 18) * S;
      ctx.font = `${Math.round(3.4 * S)}px ${CANVAS_FONT}`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      ctx.fillStyle = App.selected === stu.id ? '#ffe066' : '#fdf6e6';
      ctx.strokeStyle = 'rgba(0,0,0,.7)'; ctx.lineWidth = Math.max(2, S * 0.7);
      ctx.strokeText(stu.name, s.cx * S, ny);
      ctx.fillText(stu.name, s.cx * S, ny);

      // 감정 아이콘 (아바타 머리 위)
      const ex = (s.cx + 9) * S, ey = (s.spriteY - 2) * S;
      const key = Stage.emotionKey(st);
      const idx = EMOTION_ORDER.indexOf(key);
      if (Assets.images.emotes && idx >= 0) {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(Assets.images.emotes, idx * 16, 0, 16, 16, ex - 6 * S, ey - 8 * S, 12 * S, 12 * S);
      } else {
        ctx.font = `${Math.round(6 * S)}px ${CANVAS_FONT}`;
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        ctx.fillText(EMOTION_EMOJI[key] || '😐', ex - 3 * S, ey + 2 * S);
      }
      // 집중 급락 시 zzz
      if (st.focus !== undefined && st.focus < 25 && Math.floor(t / 700) % 2 === 0) {
        ctx.font = `${Math.round(3.6 * S)}px ${CANVAS_FONT}`;
        ctx.fillStyle = '#cfd8ff'; ctx.textAlign = 'left';
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
      drawBubble(ctx, S, s.cx * S, (s.spriteY - 10) * S, b.text);
      ctx.globalAlpha = 1;
    });
  },
};

/** 픽셀풍 말풍선 (꼬리 포함). x=꼬리 중심, yBottom=꼬리 끝 y */
function drawBubble(ctx, S, x, yBottom, text) {
  const fs = clamp(Math.round(3.6 * S), 11, 18);
  ctx.font = `${fs}px ${CANVAS_FONT}`;
  const maxW = clamp(110 * S, 140, 300);
  const lines = wrapLines(ctx, text, maxW);
  const lh = fs * 1.35;
  const w = Math.min(maxW, Math.max(...lines.map((l) => ctx.measureText(l).width))) + fs;
  const h = lines.length * lh + fs * 0.7;
  let bx = Math.round(x - w / 2);
  bx = clamp(bx, 4, ctx.canvas.width - w - 4);
  let by = Math.round(yBottom - h - 6 * S);
  by = Math.max(2, by);

  const px = Math.max(2, Math.round(S * 0.7));      // 픽셀 테두리 두께
  ctx.fillStyle = '#14161d';
  ctx.fillRect(bx - px, by - px, w + px * 2, h + px * 2);
  ctx.fillStyle = '#fbf8ef';
  ctx.fillRect(bx, by, w, h);
  // 꼬리 (계단식 = 도트 느낌)
  const tipX = clamp(Math.round(x), bx + 6, bx + w - 12);
  for (let k = 0; k < 4; k++) {
    ctx.fillStyle = '#14161d';
    ctx.fillRect(tipX - (4 - k) * px, by + h + k * px, (4 - k) * 2 * px, px);
    ctx.fillStyle = '#fbf8ef';
    ctx.fillRect(tipX - (4 - k) * px + px, by + h + k * px - 1, ((4 - k) * 2 - 2) * px, px);
  }
  ctx.fillStyle = '#1b1e28';
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
  },

  setupError(msg) {
    const el = $('#setup-error');
    el.textContent = msg;
    el.hidden = !msg;
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
      $('#teacher-input').focus();
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
    box.scrollTop = box.scrollHeight;
  },
  addSystemLine(text) { UI.addLine('system', '', text); },
  addTurnMark() {
    const box = $('#transcript');
    const div = document.createElement('div');
    div.className = 'line turnmark';
    div.textContent = `— ${App.turn}턴 · ${App.minute}분 · ${App.phase} —`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  },

  nameOf(actor) {
    const s = App.students.find((x) => x.id === actor);
    return s ? s.name : actor;
  },

  /* ── 턴 전송 ── */
  async send(rawText) {
    const input = $('#teacher-input');
    const text = (rawText !== undefined ? rawText : input.value).trim();
    if (!text || App.busy || App.ended) return;
    input.value = '';
    UI.setBusy(true);
    try {
      const r = await Api.turn(App.sessionId, text);
      UI.applyTurn(r);
      if (r.ended) await UI.showReport(r.report_markdown);
    } catch (e) {
      UI.addLine('system', '오류', e.message);
    } finally {
      UI.setBusy(false);
      input.focus();
    }
  },

  applyTurn(r) {
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
  },

  /* ── 학생 상세 카드 ── */
  selectStudent(id) {
    App.selected = id;
    if (!id) {
      $('#detail-card').hidden = true;
      $('#detail-empty').hidden = false;
      return;
    }
    $('#detail-empty').hidden = true;
    $('#detail-card').hidden = false;
    UI.renderDetail(id);
  },

  renderDetail(id) {
    const stu = App.students.find((s) => s.id === id);
    if (!stu) return;
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
    pc.imageSmoothingEnabled = false;
    pc.clearRect(0, 0, SPRITE_W, SPRITE_H);
    pc.drawImage(sprite.img, 0, 0, SPRITE_W, SPRITE_H, 0, 0, SPRITE_W, SPRITE_H);
  },

  /* ── 종료 리포트 ── */
  async showReport(md) {
    let report = md;
    if (!report) {
      try { report = (await Api.end(App.sessionId)).report_markdown; } catch (e) { report = null; }
    }
    App.reportMd = report || '# 수업 종료\n\n리포트를 생성하지 못했습니다.';
    $('#report-body').innerHTML = mdToHtml(App.reportMd);
    document.body.dataset.screen = 'report';
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

function insertCommand(cmd) {
  const input = $('#teacher-input');
  let text = cmd;
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
  $('#btn-start').addEventListener('click', UI.start);

  $('#btn-send').addEventListener('click', () => UI.send());
  $('#teacher-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) UI.send();
  });

  document.querySelectorAll('#cmd-bar button, .dc-actions button').forEach((b) => {
    b.addEventListener('click', () => insertCommand(b.dataset.cmd));
  });
  $('#dc-close').addEventListener('click', () => UI.selectStudent(null));

  $('#btn-download').addEventListener('click', async () => {
    try {
      const t = await Api.transcript(App.sessionId);
      download(`transcript_${App.sessionId}.json`, JSON.stringify(t, null, 2));
    } catch (e) {
      alert('전사를 내려받지 못했습니다: ' + e.message);
    }
  });
  $('#btn-download-md').addEventListener('click', () => {
    download(`report_${App.sessionId}.md`, App.reportMd, 'text/markdown;charset=utf-8');
  });
  $('#btn-restart').addEventListener('click', () => { location.reload(); });
});
