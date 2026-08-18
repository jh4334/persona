/* ============================================================
   학급 만들기 폼 — JSON을 몰라도 학급을 만든다

   교사에게 JSON을 손으로 쓰게 하는 것은 사실상 "만들 수 없다"와 같다.
   이 화면은 같은 결과물(학급 JSON)을 폼으로 만든다. 붙여넣기 탭은 그대로
   남겨 두어, 이미 파일을 가진 사람은 예전처럼 쓸 수 있다.

   102개 속성을 한 번에 보여 주면 아무도 채우지 않는다. 그래서
     · 기본 정보(이름·성취수준 등)만 펼쳐 두고
     · 9개 속성 그룹은 접어 둔 채, 채운 개수를 접힌 채로 보여 준다
   설계로 만들었다. 속성은 전부 선택 사항이다.
   ============================================================ */

const Builder = {
  dims: null,          // /api/dimensions 응답 (한 번만 불러 캐시)
  students: [],        // 편집 중인 학생 배열
  openIdx: -1,         // 펼쳐 둔 학생 카드 (한 번에 하나)
  seq: 0,              // 학생 id 자동 부여용

  ACHIEVEMENT: ['상', '중상', '중', '중하', '하'],

  /* ── 열기 / 닫기 ─────────────────────────────────────────── */

  async open() {
    if (!this.dims) {
      try {
        this.dims = await Api.dimensions();
      } catch (e) {
        this.dims = { groups: [] };     // 카탈로그가 없어도 기본 정보로는 만들 수 있다
      }
    }
    if (!this.students.length) this.addStudent();
    this.render();
  },

  reset() {
    this.students = [];
    this.openIdx = -1;
    this.seq = 0;
    $('#bd-class-name').value = '';
    $('#bd-grade').value = '';
    $('#bd-desc').value = '';
    this.addStudent();
    this.render();
  },

  /* ── 학생 다루기 ─────────────────────────────────────────── */

  blank() {
    this.seq += 1;
    return {
      id: 'S' + String(this.seq).padStart(2, '0'),
      name: '', achievement_level: '중',
      prior_knowledge: '', learning_style: '', interests: '',
      personality: '', social: '', notes: '',
      attrs: {},          // {그룹키: {속성명: 값}}
    };
  },

  addStudent() {
    this.students.push(this.blank());
    this.openIdx = this.students.length - 1;
  },

  /** 한 명을 통째로 복제 — 비슷한 학생 여럿을 만들 때 훨씬 빠르다 */
  copyStudent(i) {
    const src = this.students[i];
    const copy = JSON.parse(JSON.stringify(src));
    this.seq += 1;
    copy.id = 'S' + String(this.seq).padStart(2, '0');
    copy.name = src.name ? src.name + ' (사본)' : '';
    this.students.splice(i + 1, 0, copy);
    this.openIdx = i + 1;
  },

  removeStudent(i) {
    this.students.splice(i, 1);
    if (!this.students.length) this.addStudent();
    this.openIdx = Math.min(this.openIdx, this.students.length - 1);
  },

  /** "상 2, 중 6, 하 4" 식 구성으로 학생 초안을 한 번에 만든다 */
  quickFill(total, dist) {
    const names = [];
    const levels = [];
    Object.keys(dist).forEach((lv) => {
      for (let i = 0; i < dist[lv]; i++) levels.push(lv);
    });
    while (levels.length < total) levels.push('중');
    levels.length = total;
    this.students = [];
    this.seq = 0;
    levels.forEach((lv, i) => {
      const s = this.blank();
      s.achievement_level = lv;
      s.name = '학생' + String(i + 1).padStart(2, '0');
      this.students.push(s);
    });
    this.openIdx = 0;
    names.length = 0;
  },

  /* ── 그리기 ──────────────────────────────────────────────── */

  attrCount(s) {
    let n = 0;
    Object.keys(s.attrs || {}).forEach((g) => {
      Object.keys(s.attrs[g] || {}).forEach((k) => { if (s.attrs[g][k]) n += 1; });
    });
    return n;
  },

  render() {
    const box = $('#bd-students');
    box.innerHTML = this.students.map((s, i) => this.studentCard(s, i)).join('');
    $('#bd-count').textContent = `${this.students.length}명`;
    this.bindCards();
  },

  studentCard(s, i) {
    const open = i === this.openIdx;
    const filled = this.attrCount(s);
    const head =
      `<button type="button" class="bd-head" data-act="toggle" data-i="${i}" aria-expanded="${open}">
         <span class="bd-num">${i + 1}</span>
         <span class="bd-name">${esc(s.name) || '<i>이름 없음</i>'}</span>
         <span class="bd-lv">${esc(s.achievement_level)}</span>
         ${filled ? `<span class="bd-attrs">속성 ${filled}</span>` : ''}
         <span class="bd-caret">${open ? '▾' : '▸'}</span>
       </button>`;
    if (!open) return `<div class="bd-card">${head}</div>`;

    const f = (label, key, ph) =>
      `<label class="bd-field"><span>${label}</span>
         <input type="text" data-i="${i}" data-k="${key}"
                value="${esc(s[key] || '')}" placeholder="${esc(ph || '')}"></label>`;

    return `<div class="bd-card open">${head}
      <div class="bd-body">
        <div class="bd-row">
          <label class="bd-field"><span>이름 *</span>
            <input type="text" data-i="${i}" data-k="name" value="${esc(s.name)}"
                   placeholder="김하늘" required></label>
          <label class="bd-field bd-narrow"><span>성취 수준</span>
            <select data-i="${i}" data-k="achievement_level">
              ${this.ACHIEVEMENT.map((v) =>
                `<option ${v === s.achievement_level ? 'selected' : ''}>${v}</option>`).join('')}
            </select></label>
        </div>
        ${f('사전 지식', 'prior_knowledge', '분수 개념은 알지만 비는 처음')}
        ${f('학습 스타일', 'learning_style', '시각 자료를 좋아함')}
        ${f('흥미 / 관심사', 'interests', '축구, 게임  (쉼표로 구분)')}
        ${f('성격', 'personality', '조용하지만 끈기 있음')}
        ${f('교우 관계', 'social', '짝과 잘 협력함')}
        ${f('교사 메모', 'notes', '발표를 매우 부담스러워함')}
        ${this.attrGroups(s, i)}
        <div class="bd-card-actions">
          <button type="button" data-act="copy" data-i="${i}">이 학생 복제</button>
          <button type="button" class="danger" data-act="del" data-i="${i}">삭제</button>
        </div>
      </div></div>`;
  },

  attrGroups(s, i) {
    if (!this.dims || !this.dims.groups || !this.dims.groups.length) return '';
    return `<div class="bd-groups">${this.dims.groups.map((g) => {
      const cur = (s.attrs && s.attrs[g.key]) || {};
      const n = Object.keys(cur).filter((k) => cur[k]).length;
      return `<details class="bd-group">
        <summary>${esc(g.label)}${n ? ` <b>${n}</b>` : ''}
          <i>${esc(g.description || '')}</i></summary>
        <div class="bd-group-body">${g.dimensions.map((d) => {
          const v = cur[d.key] || '';
          const control = (d.values && d.values.length)
            ? `<select data-i="${i}" data-g="${esc(g.key)}" data-d="${esc(d.key)}">
                 <option value="">—</option>
                 ${d.values.map((x) =>
                   `<option ${x === v ? 'selected' : ''}>${esc(x)}</option>`).join('')}
               </select>`
            : `<input type="text" data-i="${i}" data-g="${esc(g.key)}" data-d="${esc(d.key)}"
                      value="${esc(v)}" placeholder="자유 서술">`;
          return `<label class="bd-attr" title="${esc(d.description || '')}">
                    <span>${esc(d.key)}</span>${control}</label>`;
        }).join('')}</div>
      </details>`;
    }).join('')}</div>`;
  },

  /** 속성을 채운 개수를 그룹 머리글과 학생 머리글에 즉시 반영한다 */
  refreshCounts(el, s) {
    const det = el.closest('.bd-group');
    if (det) {
      const g = el.dataset.g;
      const n = Object.keys(s.attrs[g] || {}).filter((k) => s.attrs[g][k]).length;
      const sum = det.querySelector('summary');
      let b = sum.querySelector('b');
      if (n && !b) {
        b = document.createElement('b');
        sum.insertBefore(b, sum.querySelector('i'));
      }
      if (b) {
        if (n) b.textContent = String(n);
        else b.remove();
      }
    }
    const card = el.closest('.bd-card');
    if (!card) return;
    const total = this.attrCount(s);
    let badge = card.querySelector('.bd-attrs');
    if (total && !badge) {
      badge = document.createElement('span');
      badge.className = 'bd-attrs';
      card.querySelector('.bd-caret').before(badge);
    }
    if (badge) {
      if (total) badge.textContent = `속성 ${total}`;
      else badge.remove();
    }
  },

  /** 카드 안의 입력은 이벤트 위임으로 받는다 (다시 그려도 리스너가 새지 않게) */
  bindCards() {
    const box = $('#bd-students');
    if (box.dataset.bound) return;
    box.dataset.bound = '1';

    box.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-act]');
      if (!btn) return;
      const i = Number(btn.dataset.i);
      if (btn.dataset.act === 'toggle') { this.openIdx = this.openIdx === i ? -1 : i; this.render(); }
      else if (btn.dataset.act === 'copy') { this.copyStudent(i); this.render(); }
      else if (btn.dataset.act === 'del') { this.removeStudent(i); this.render(); }
    });

    const onEdit = (e) => {
      const el = e.target;
      const i = Number(el.dataset.i);
      if (Number.isNaN(i) || !this.students[i]) return;
      if (el.dataset.g) {                       // 속성 그룹
        const s = this.students[i];
        s.attrs[el.dataset.g] = s.attrs[el.dataset.g] || {};
        s.attrs[el.dataset.g][el.dataset.d] = el.value;
        // 전체를 다시 그리면 펼친 그룹이 닫히고 포커스를 잃는다. 숫자만 제자리에서 고친다.
        this.refreshCounts(el, s);
      } else if (el.dataset.k) {
        this.students[i][el.dataset.k] = el.value;
        // 이름·성취수준은 접힌 머리글에도 보인다. 편집 중에 카드를 통째로 다시
        // 그리면 포커스를 잃고, blur 도중이면 브라우저가 innerHTML 교체를 거부한다.
        // 그래서 바뀐 글자만 제자리에서 고친다.
        const card = el.closest('.bd-card');
        if (!card) return;
        if (el.dataset.k === 'name') {
          const slot = card.querySelector('.bd-name');
          if (slot) slot.innerHTML = el.value.trim() ? esc(el.value) : '<i>이름 없음</i>';
        } else if (el.dataset.k === 'achievement_level') {
          const slot = card.querySelector('.bd-lv');
          if (slot) slot.textContent = el.value;
        }
      }
    };
    box.addEventListener('input', onEdit);
    box.addEventListener('change', onEdit);
  },

  /* ── 결과물 ──────────────────────────────────────────────── */

  /** 폼 → 학급 JSON. 서버가 받는 것과 같은 모양 */
  toJSON() {
    const out = {
      class_name: ($('#bd-class-name').value || '').trim(),
      grade: ($('#bd-grade').value || '').trim(),
      description: ($('#bd-desc').value || '').trim(),
      students: this.students.map((s) => {
        const o = { id: s.id, name: (s.name || '').trim() };
        ['achievement_level', 'prior_knowledge', 'learning_style',
         'personality', 'social', 'notes'].forEach((k) => {
          if ((s[k] || '').trim()) o[k] = s[k].trim();
        });
        const tags = (s.interests || '').split(',').map((t) => t.trim()).filter(Boolean);
        if (tags.length) o.interests = tags;
        Object.keys(s.attrs || {}).forEach((g) => {
          const kept = {};
          Object.keys(s.attrs[g]).forEach((k) => {
            if ((s.attrs[g][k] || '').trim()) kept[k] = s.attrs[g][k].trim();
          });
          if (Object.keys(kept).length) o[g] = kept;   // 빈 그룹은 넣지 않는다
        });
        return o;
      }),
    };
    if (!out.description) delete out.description;
    if (!out.grade) delete out.grade;
    return out;
  },

  /** 저장 전에 폼에서 바로 잡을 수 있는 것만 미리 짚어 준다 */
  precheck() {
    if (!($('#bd-class-name').value || '').trim()) return '학급 이름을 입력해 주세요.';
    const blank = this.students.findIndex((s) => !(s.name || '').trim());
    if (blank >= 0) {
      this.openIdx = blank;
      this.render();
      return `${blank + 1}번 학생의 이름을 입력해 주세요.`;
    }
    const names = this.students.map((s) => s.name.trim());
    const dup = names.find((n, i) => names.indexOf(n) !== i);
    if (dup) return `학생 이름이 겹칩니다: ${dup} — 구분할 수 있게 바꿔 주세요.`;
    return '';
  },
};
