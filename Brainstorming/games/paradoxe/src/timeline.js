/**
 * PARADOXE - the time strip.
 *
 * One lane per actor: the live run on top, then every clone from newest to
 * oldest. Each lane shows how far its tape runs and where its marking events
 * sit, so "the clone lets go of the button at two thirds of the run" is a thing
 * you can read instead of a thing you have to remember.
 */

import { PALETTE } from './config.js';

const EVENT_COLORS = {
  'b+': '#ffb347',
  'b-': '#7a5a2a',
  grab: '#d79a4a',
  drop: '#8be9ff',
  tp: '#37d7ff',
};

function eventColor(key) {
  if (key.startsWith('b+')) return EVENT_COLORS['b+'];
  if (key.startsWith('b-')) return EVENT_COLORS['b-'];
  if (key.startsWith('grab')) return EVENT_COLORS.grab;
  if (key.startsWith('drop')) return EVENT_COLORS.drop;
  if (key.startsWith('tp')) return EVENT_COLORS.tp;
  return '#ffffff';
}

function cssColor(hexValue) {
  return '#' + hexValue.toString(16).padStart(6, '0');
}

export function createTimeline(canvas) {
  const ctx = canvas.getContext('2d');
  let dpr = 1;
  let cssW = 0;
  let cssH = 0;

  const tl = { canvas };

  tl.resize = function resize() {
    const rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    cssW = Math.max(120, rect.width);
    cssH = Math.max(40, rect.height);
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
  };

  /**
   * @param {object} level current level (for total tick count)
   * @param {Array} recordings clone tapes, oldest first
   * @param {number} tick current simulation tick
   * @param {number} rewind 0..1 rewind progress, drives the sweep back
   */
  tl.draw = function draw(level, recordings, tick, rewind) {
    if (!cssW) tl.resize();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const laneCount = 1 + recordings.length;
    const padX = 10;
    const padY = 6;
    const innerW = cssW - padX * 2;
    const gap = 3;
    const laneH = Math.max(4, Math.min(11, (cssH - padY * 2 - gap * (laneCount - 1)) / laneCount));
    const total = level.ticks;

    for (let lane = 0; lane < laneCount; lane++) {
      const y = padY + lane * (laneH + gap);
      const isLive = lane === 0;
      const rec = isLive ? null : recordings[recordings.length - lane];
      const color = isLive ? cssColor(PALETTE.player) : cssColor(PALETTE.clones[(recordings.length - lane) % PALETTE.clones.length]);

      ctx.fillStyle = 'rgba(255,255,255,0.07)';
      ctx.fillRect(padX, y, innerW, laneH);

      const span = isLive ? tick / total : rec.ticks / total;
      const width = innerW * Math.min(1, Math.max(0, span));
      ctx.fillStyle = color;
      ctx.globalAlpha = isLive ? 0.85 : 0.42;
      ctx.fillRect(padX, y, width, laneH);
      ctx.globalAlpha = 1;

      if (!isLive) {
        // Frozen tail: what the clone does after its tape ends (it stands still).
        ctx.fillStyle = 'rgba(255,255,255,0.10)';
        ctx.fillRect(padX + width, y, innerW - width, laneH);
        for (let i = 0; i < rec.events.length; i++) {
          const e = rec.events[i];
          const c = eventColor(e.key);
          if (c === '#ffffff') continue;
          const ex = padX + innerW * Math.min(1, e.tick / total);
          ctx.fillStyle = c;
          ctx.fillRect(ex - 1, y - 1, 2, laneH + 2);
        }
      }
    }

    // Play head.
    const headT = rewind > 0 ? (tick / total) * (1 - rewind) : tick / total;
    const hx = padX + innerW * Math.min(1, Math.max(0, headT));
    ctx.fillStyle = rewind > 0 ? '#ff8bd2' : '#ffffff';
    ctx.fillRect(hx - 1, 2, 2, cssH - 4);
    ctx.fillStyle = rewind > 0 ? 'rgba(255,139,210,0.25)' : 'rgba(255,255,255,0.18)';
    ctx.fillRect(hx - 5, 2, 10, cssH - 4);
  };

  return tl;
}
