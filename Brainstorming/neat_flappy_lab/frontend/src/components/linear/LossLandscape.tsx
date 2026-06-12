import { useMemo } from 'react'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LandscapePoint { x: number; y: number }

// ─── Constants ───────────────────────────────────────────────────────────────

const W_MIN = -2.2
const W_MAX = 3.2
const B_MIN = -1.8
const B_MAX = 2.0

const W_CELLS = 56
const B_CELLS = 44

// SVG layout
const VB_W = 600
const VB_H = 460

const MARGIN_LEFT = 44
const MARGIN_RIGHT = 52   // space for colorbar
const MARGIN_TOP = 12
const MARGIN_BOTTOM = 34

const PLOT_W = VB_W - MARGIN_LEFT - MARGIN_RIGHT  // 504
const PLOT_H = VB_H - MARGIN_TOP - MARGIN_BOTTOM   // 414

const CELL_W = PLOT_W / W_CELLS   // ~9
const CELL_H = PLOT_H / B_CELLS   // ~9.4

// Color palette stops — loss (compressed) in [0,1] → color
// 0.0 → deep bg teal  #1a2333
// 0.2 → dark teal     #0f2a2a
// 0.45 → teal         #4fd1c5
// 0.72 → warm amber   #f6c177
// 1.0 → danger red    #f7768e
const COLOR_STOPS: Array<{ t: number; r: number; g: number; b: number }> = [
  { t: 0.00, r: 0x1a, g: 0x23, b: 0x33 },
  { t: 0.18, r: 0x0f, g: 0x2a, b: 0x2a },
  { t: 0.42, r: 0x4f, g: 0xd1, b: 0xc5 },
  { t: 0.70, r: 0xf6, g: 0xc1, b: 0x77 },
  { t: 1.00, r: 0xf7, g: 0x76, b: 0x8e },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function mse(w: number, b: number, samples: LandscapePoint[]): number {
  if (samples.length === 0) return 0
  let sum = 0
  for (const s of samples) {
    const diff = w * s.x + b - s.y
    sum += diff * diff
  }
  return sum / samples.length
}

/** Map a value in [0,1] through the color stops, return "rgb(r,g,b)" */
function lerpColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t))
  let lo = COLOR_STOPS[0]
  let hi = COLOR_STOPS[COLOR_STOPS.length - 1]
  for (let i = 0; i < COLOR_STOPS.length - 1; i++) {
    if (clamped >= COLOR_STOPS[i].t && clamped <= COLOR_STOPS[i + 1].t) {
      lo = COLOR_STOPS[i]
      hi = COLOR_STOPS[i + 1]
      break
    }
  }
  const range = hi.t - lo.t
  const f = range < 1e-9 ? 0 : (clamped - lo.t) / range
  const r = Math.round(lo.r + f * (hi.r - lo.r))
  const g = Math.round(lo.g + f * (hi.g - lo.g))
  const b = Math.round(lo.b + f * (hi.b - lo.b))
  return `rgb(${r},${g},${b})`
}

/** Map w value → SVG x pixel (within plot area, offset by MARGIN_LEFT) */
function wToX(w: number): number {
  return MARGIN_LEFT + ((w - W_MIN) / (W_MAX - W_MIN)) * PLOT_W
}

/** Map b value → SVG y pixel (b axis is vertical; larger b = lower y in math → lower y in SVG) */
function bToY(b: number): number {
  return MARGIN_TOP + ((B_MAX - b) / (B_MAX - B_MIN)) * PLOT_H
}

function round1(n: number): number {
  return Math.round(n * 10) / 10
}

// ─── Precomputed grid (memoised on samples) ───────────────────────────────────

interface GridCell {
  x: number   // SVG x of top-left corner
  y: number   // SVG y of top-left corner
  fill: string
}

function buildGrid(samples: LandscapePoint[]): GridCell[] {
  // First pass: compute raw MSE values
  const rawValues: number[] = new Array(W_CELLS * B_CELLS)
  let maxLoss = 0

  for (let bi = 0; bi < B_CELLS; bi++) {
    const bVal = B_MAX - bi * (B_MAX - B_MIN) / B_CELLS
    for (let wi = 0; wi < W_CELLS; wi++) {
      const wVal = W_MIN + wi * (W_MAX - W_MIN) / W_CELLS
      const loss = mse(wVal, bVal, samples)
      rawValues[bi * W_CELLS + wi] = loss
      if (loss > maxLoss) maxLoss = loss
    }
  }

  // Second pass: normalise + compress + assign color
  const cells: GridCell[] = []
  for (let bi = 0; bi < B_CELLS; bi++) {
    const bVal = B_MAX - bi * (B_MAX - B_MIN) / B_CELLS
    const svgY = Math.round(bToY(bVal) * 10) / 10
    for (let wi = 0; wi < W_CELLS; wi++) {
      const wVal = W_MIN + wi * (W_MAX - W_MIN) / W_CELLS
      const svgX = Math.round(wToX(wVal) * 10) / 10
      const raw = rawValues[bi * W_CELLS + wi]
      const norm = maxLoss > 0 ? raw / maxLoss : 0
      // sqrt compression for perceptual uniformity
      const compressed = Math.sqrt(norm)
      cells.push({ x: svgX, y: svgY, fill: lerpColor(compressed) })
    }
  }
  return cells
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AxisLabels(): JSX.Element {
  // W axis ticks (bottom)
  const wTicks = [-2, -1, 0, 1, 2, 3]
  // B axis ticks (left)
  const bTicks = [-1.5, -1, -0.5, 0, 0.5, 1, 1.5]

  return (
    <g style={{ fontSize: 10, fill: '#9fb0c8', fontFamily: 'monospace' }}>
      {/* W axis ticks */}
      {wTicks.map(w => (
        <g key={w}>
          <line
            x1={round1(wToX(w))} y1={MARGIN_TOP + PLOT_H}
            x2={round1(wToX(w))} y2={MARGIN_TOP + PLOT_H + 4}
            stroke="#61708a" strokeWidth={1}
          />
          <text
            x={round1(wToX(w))} y={MARGIN_TOP + PLOT_H + 14}
            textAnchor="middle"
          >{w}</text>
        </g>
      ))}
      {/* W axis label */}
      <text
        x={MARGIN_LEFT + PLOT_W / 2} y={VB_H - 2}
        textAnchor="middle" style={{ fontSize: 11, fill: '#e7edf7' }}
      >w</text>

      {/* B axis ticks */}
      {bTicks.map(b => (
        <g key={b}>
          <line
            x1={MARGIN_LEFT - 4} y1={round1(bToY(b))}
            x2={MARGIN_LEFT}     y2={round1(bToY(b))}
            stroke="#61708a" strokeWidth={1}
          />
          <text
            x={MARGIN_LEFT - 7} y={round1(bToY(b)) + 3}
            textAnchor="end"
          >{b}</text>
        </g>
      ))}
      {/* B axis label */}
      <text
        x={10} y={MARGIN_TOP + PLOT_H / 2}
        textAnchor="middle" style={{ fontSize: 11, fill: '#e7edf7' }}
        transform={`rotate(-90, 10, ${MARGIN_TOP + PLOT_H / 2})`}
      >b</text>
    </g>
  )
}

function Colorbar(): JSX.Element {
  const cbX = VB_W - MARGIN_RIGHT + 8
  const cbY = MARGIN_TOP
  const cbW = 12
  const cbH = PLOT_H
  const gradId = 'lossGrad'

  // Build gradient stops from COLOR_STOPS (reversed: high loss at top)
  const gradStops = [...COLOR_STOPS].reverse().map(s => ({
    offset: `${Math.round((1 - s.t) * 100)}%`,
    color: `rgb(${s.r},${s.g},${s.b})`,
  }))

  return (
    <g>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          {gradStops.map(s => (
            <stop key={s.offset} offset={s.offset} stopColor={s.color} />
          ))}
        </linearGradient>
      </defs>
      <rect x={cbX} y={cbY} width={cbW} height={cbH} fill={`url(#${gradId})`} rx={2} />
      <rect x={cbX} y={cbY} width={cbW} height={cbH} fill="none" stroke="#25304a" strokeWidth={0.5} rx={2} />
      {/* Labels */}
      <text x={cbX + cbW + 3} y={cbY + 8} style={{ fontSize: 9, fill: '#9fb0c8', fontFamily: 'monospace' }}>high</text>
      <text x={cbX + cbW + 3} y={cbY + cbH} style={{ fontSize: 9, fill: '#9fb0c8', fontFamily: 'monospace' }}>low</text>
      {/* "loss" rotated label */}
      <text
        x={cbX + cbW / 2} y={cbY + cbH / 2}
        textAnchor="middle"
        style={{ fontSize: 9, fill: '#61708a', fontFamily: 'monospace' }}
        transform={`rotate(90, ${cbX + cbW / 2}, ${cbY + cbH / 2})`}
      >loss</text>
    </g>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function LossLandscape({
  samples,
  w,
  b,
  trajectory,
}: {
  samples: LandscapePoint[]
  w: number
  b: number
  trajectory: { w: number; b: number }[]
}): JSX.Element {

  // Memoised grid depends ONLY on samples (not w/b/trajectory)
  const gridCells = useMemo(
    () => buildGrid(samples),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [samples]
  )

  // Trajectory polyline points
  const trajectoryPoints = trajectory
    .map(pt => `${round1(wToX(pt.w))},${round1(bToY(pt.b))}`)
    .join(' ')

  // Current position in SVG coords
  const cx = round1(wToX(w))
  const cy = round1(bToY(b))

  // Cell dimensions (add small epsilon to avoid gaps)
  const rW = Math.ceil(CELL_W + 0.5)
  const rH = Math.ceil(CELL_H + 0.5)

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      width="100%"
      height="100%"
      style={{ display: 'block', background: '#131a26' }}
    >
      {/* ── Heatmap cells ── */}
      <g>
        {gridCells.map((cell, i) => (
          <rect
            key={i}
            x={cell.x}
            y={cell.y}
            width={rW}
            height={rH}
            fill={cell.fill}
          />
        ))}
      </g>

      {/* ── Plot border ── */}
      <rect
        x={MARGIN_LEFT} y={MARGIN_TOP}
        width={PLOT_W} height={PLOT_H}
        fill="none" stroke="#25304a" strokeWidth={0.5}
      />

      {/* ── Trajectory polyline ── */}
      {trajectory.length >= 2 && (
        <polyline
          points={trajectoryPoints}
          fill="none"
          stroke="#e7edf7"
          strokeWidth={2}
          strokeOpacity={0.85}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {/* ── Trajectory start dot (if trajectory has points) ── */}
      {trajectory.length >= 1 && (
        <circle
          cx={round1(wToX(trajectory[0].w))}
          cy={round1(bToY(trajectory[0].b))}
          r={3}
          fill="#61708a"
          fillOpacity={0.7}
        />
      )}

      {/* ── Current position: outer ring + inner dot ── */}
      <circle
        cx={cx} cy={cy}
        r={8}
        fill="none"
        stroke="#4fd1c5"
        strokeWidth={2}
        strokeOpacity={0.9}
      />
      <circle
        cx={cx} cy={cy}
        r={3.5}
        fill="#4fd1c5"
        fillOpacity={0.95}
      />
      {/* Subtle glow ring */}
      <circle
        cx={cx} cy={cy}
        r={12}
        fill="none"
        stroke="#4fd1c5"
        strokeWidth={0.8}
        strokeOpacity={0.3}
      />

      {/* ── Axes & labels ── */}
      <AxisLabels />

      {/* ── Colorbar ── */}
      <Colorbar />
    </svg>
  )
}
