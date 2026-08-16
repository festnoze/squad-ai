/**
 * OVERCLOCK - the programming panel.
 *
 * Plain DOM on top of the canvas: drag and drop, right click and keyboard all
 * come for free, and text stays crisp at any resolution. The panel never reads
 * the warehouse, only the program.
 */

import { OPS } from '../program.js';

export function createPanel(opts) {
  const paletteEl = opts.paletteEl;
  const procsEl = opts.procsEl;
  const onChange = opts.onChange || (() => {});
  const onSound = opts.onSound || (() => {});

  let level = null;
  let program = null;
  let selectedOp = null;
  let sel = { proc: 0, slot: 0 };
  let editable = true;
  let slotEls = [];
  let palEls = [];
  let marked = null;

  function opLabel(op) {
    const def = OPS[op];
    if (!def) return op;
    if (def.paint) return 'PEINDRE';
    return def.label;
  }

  function buildPalette() {
    paletteEl.textContent = '';
    palEls = [];
    level.ops.forEach((op, i) => {
      const def = OPS[op];
      if (!def) return;
      const b = document.createElement('button');
      b.className = 'pal';
      b.type = 'button';
      b.dataset.op = op;
      b.draggable = true;
      b.title = def.help + (i < 9 ? '  (touche ' + (i + 1) + ')' : '');
      b.innerHTML =
        '<span class="k">' + (i < 9 ? i + 1 : '') + '</span>' +
        '<span class="g">' + def.glyph + '</span>' +
        '<span class="n">' + opLabel(op) + '</span>';
      b.addEventListener('click', () => {
        if (!editable) return;
        selectedOp = selectedOp === op ? null : op;
        onSound('ui');
        refreshPalette();
      });
      b.addEventListener('dragstart', (e) => {
        selectedOp = op;
        refreshPalette();
        e.dataTransfer.setData('text/plain', op);
        e.dataTransfer.effectAllowed = 'copy';
      });
      paletteEl.appendChild(b);
      palEls.push(b);
    });
    refreshPalette();
  }

  function refreshPalette() {
    for (const b of palEls) b.classList.toggle('sel', b.dataset.op === selectedOp);
  }

  function buildProcs() {
    procsEl.textContent = '';
    slotEls = [];
    program.procs.forEach((proc, pi) => {
      const wrap = document.createElement('div');
      wrap.className = 'proc';

      const head = document.createElement('div');
      head.className = 'proc-head';
      const used = proc.slots.filter(Boolean).length;
      head.innerHTML = '<b>' + proc.name + '</b><span>' + used + ' / ' + proc.slots.length + '</span>';
      wrap.appendChild(head);

      const row = document.createElement('div');
      row.className = 'slots';
      const refs = [];
      proc.slots.forEach((_, si) => {
        const b = document.createElement('button');
        b.className = 'slot';
        b.type = 'button';
        b.dataset.proc = String(pi);
        b.dataset.slot = String(si);
        b.innerHTML = '<span class="g"></span><span class="c"></span>';
        b.addEventListener('click', () => onSlotClick(pi, si));
        b.addEventListener('contextmenu', (e) => {
          e.preventDefault();
          if (!editable) return;
          sel = { proc: pi, slot: si };
          if (program.clear(pi, si)) {
            onSound('clear');
            changed();
          } else {
            paint();
          }
        });
        b.addEventListener('dragover', (e) => {
          if (!editable) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = 'copy';
          b.classList.add('over');
        });
        b.addEventListener('dragleave', () => b.classList.remove('over'));
        b.addEventListener('drop', (e) => {
          e.preventDefault();
          b.classList.remove('over');
          if (!editable) return;
          const op = e.dataTransfer.getData('text/plain');
          if (!OPS[op] || !level.ops.includes(op)) return;
          sel = { proc: pi, slot: si };
          if (program.set(pi, si, op, null)) {
            onSound('place');
            changed();
          }
        });
        row.appendChild(b);
        refs.push(b);
      });
      wrap.appendChild(row);
      procsEl.appendChild(wrap);
      slotEls.push(refs);
    });
    paint();
  }

  function onSlotClick(pi, si) {
    if (!editable) return;
    sel = { proc: pi, slot: si };
    const current = program.get(pi, si);
    if (selectedOp) {
      if (program.set(pi, si, selectedOp, current ? current.cond : null)) {
        onSound('place');
        advance();
        changed();
        return;
      }
    }
    if (current && level.colors.length) {
      if (program.cycleCond(pi, si, level.colors)) {
        onSound('ui');
        changed();
        return;
      }
    }
    paint();
  }

  function advance() {
    const proc = program.procs[sel.proc];
    if (sel.slot + 1 < proc.slots.length) sel.slot++;
    else if (sel.proc + 1 < program.procs.length) {
      sel.proc++;
      sel.slot = 0;
    }
  }

  function changed() {
    buildProcs();
    onChange();
  }

  /** Repaints slot contents and states without rebuilding the DOM. */
  function paint() {
    for (let pi = 0; pi < slotEls.length; pi++) {
      const proc = program.procs[pi];
      for (let si = 0; si < slotEls[pi].length; si++) {
        const el = slotEls[pi][si];
        const inst = proc.slots[si];
        el.className = 'slot';
        if (inst) {
          const def = OPS[inst.op];
          el.classList.add('filled');
          el.dataset.op = inst.op;
          el.querySelector('.g').textContent = def ? def.glyph : '?';
          if (inst.cond) el.classList.add('cond-' + inst.cond);
          el.title = (def ? def.help : inst.op) + (inst.cond ? ' - seulement sur ' + inst.cond.toUpperCase() : '');
        } else {
          delete el.dataset.op;
          el.querySelector('.g').textContent = '';
          el.title = 'Slot vide';
        }
        if (sel.proc === pi && sel.slot === si) el.classList.add('sel');
        if (marked && marked.proc === pi && marked.slot === si) el.classList.add(marked.cls);
      }
    }
  }

  const panel = {
    get selection() {
      return sel;
    },

    setLevel(lv, prog) {
      level = lv;
      program = prog;
      selectedOp = null;
      sel = { proc: 0, slot: 0 };
      marked = null;
      buildPalette();
      buildProcs();
    },

    refresh() {
      if (!program) return;
      buildProcs();
    },

    setEditable(v) {
      editable = !!v;
      paletteEl.style.opacity = editable ? '1' : '0.45';
      procsEl.style.opacity = editable ? '1' : '0.9';
    },

    /** cls is 'exec' for a running instruction, 'skip' for a condition miss. */
    highlight(proc, slot, cls) {
      marked = proc >= 0 && slot >= 0 ? { proc, slot, cls: cls || 'exec' } : null;
      paint();
    },

    clearHighlight() {
      marked = null;
      paint();
    },

    /** Returns true when the key was consumed, so main.js can stop there. */
    handleKey(e) {
      if (!program || !editable) return false;
      const k = e.key;

      if (k >= '1' && k <= '9') {
        const op = level.ops[Number(k) - 1];
        if (!op) return false;
        const cur = program.get(sel.proc, sel.slot);
        if (program.set(sel.proc, sel.slot, op, cur ? cur.cond : null)) {
          onSound('place');
          advance();
          changed();
        }
        return true;
      }

      switch (k) {
        case 'ArrowRight':
          moveSel(1);
          return true;
        case 'ArrowLeft':
          moveSel(-1);
          return true;
        case 'ArrowDown':
          moveProc(1);
          return true;
        case 'ArrowUp':
          moveProc(-1);
          return true;
        case 'Delete':
        case 'Backspace':
          if (program.clear(sel.proc, sel.slot)) {
            onSound('clear');
            changed();
          }
          return true;
        case 'c':
        case 'C': {
          if (!level.colors.length) return false;
          if (program.cycleCond(sel.proc, sel.slot, level.colors)) {
            onSound('ui');
            changed();
          }
          return true;
        }
        default:
          return false;
      }
    },

    dispose() {
      paletteEl.textContent = '';
      procsEl.textContent = '';
      slotEls = [];
      palEls = [];
    },
  };

  function moveSel(d) {
    const proc = program.procs[sel.proc];
    const s = sel.slot + d;
    if (s < 0) {
      if (sel.proc > 0) {
        sel.proc--;
        sel.slot = program.procs[sel.proc].slots.length - 1;
      } else sel.slot = 0;
    } else if (s >= proc.slots.length) {
      if (sel.proc + 1 < program.procs.length) {
        sel.proc++;
        sel.slot = 0;
      } else sel.slot = proc.slots.length - 1;
    } else sel.slot = s;
    paint();
  }

  function moveProc(d) {
    const p = sel.proc + d;
    if (p < 0 || p >= program.procs.length) return;
    sel.proc = p;
    sel.slot = Math.min(sel.slot, program.procs[p].slots.length - 1);
    paint();
  }

  return panel;
}
