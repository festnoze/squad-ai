import { Fragment, type ReactNode, useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Customized,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { LessonId } from './CurriculumNav'
import { LossLandscape } from './linear/LossLandscape'
import { ExperimentCards, type Experiment } from './linear/ExperimentCards'
import { NetworkDiagram } from './linear/NetworkDiagram'

const chart = {
  sample: '#f6c177',
  line: '#4fd1c5',
  line2: '#7c9cff',
  grid: '#25304a',
  tick: '#9fb0c8',
  bg: '#131a26',
  neg: '#f7768e',
  ok: '#9ece6a',
} as const

const tooltipStyle = {
  background: chart.bg,
  border: `1px solid ${chart.grid}`,
  borderRadius: 8,
  color: '#e7edf7',
} as const

type IconName = 'play' | 'pause' | 'step' | 'reset'

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="btn-icon" viewBox="0 0 24 24" aria-hidden="true">
      {name === 'play' && <path d="M8 5v14l11-7z" />}
      {name === 'pause' && (
        <>
          <path d="M7 5h4v14H7z" />
          <path d="M13 5h4v14h-4z" />
        </>
      )}
      {name === 'step' && (
        <>
          <path d="M6 5v14l8-7z" />
          <path d="M17 5h2v14h-2z" />
        </>
      )}
      {name === 'reset' && (
        <path d="M12 5a7 7 0 1 1-6.2 10.2l1.8-.9A5 5 0 1 0 12 7H8.8l2.6 2.6L10 11 5 6l5-5 1.4 1.4L8.8 5z" />
      )}
    </svg>
  )
}

interface Point {
  x: number
  y: number
}

interface HistoryRow {
  step: number
  loss: number
  [key: string]: number
}

function rng(seed: number) {
  let t = seed + 0x6d2b79f5
  return () => {
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function noise(rand: () => number, scale: number) {
  return (rand() + rand() + rand() + rand() - 2) * scale
}

function dataNoise(rand: () => number, scale: number) {
  const base = noise(rand, scale * 0.7)
  const outlierChance = Math.min(0.32, scale * 0.24)
  const outlier = rand() < outlierChance ? noise(rand, scale * 1.9) : 0
  return base + outlier
}

function round(n: number, digits = 5) {
  const p = 10 ** digits
  return Math.round(n * p) / p
}

function lineGrid(from = -1.8, to = 1.8, count = 70) {
  return Array.from({ length: count }, (_, i) => from + ((to - from) * i) / (count - 1))
}

function useLoop(running: boolean, delayMs: number, onTick: () => void) {
  useEffect(() => {
    if (!running) return undefined
    const id = window.setInterval(onTick, delayMs)
    return () => window.clearInterval(id)
  }, [delayMs, onTick, running])
}

function LessonHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="lesson-header">
      <span className="lesson-eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  )
}

function PointLineChart({
  samples,
  lines,
  residuals,
  xDomain = [-1.9, 1.9],
}: {
  samples: Point[]
  lines: { name: string; data: Point[]; color: string; dash?: string }[]
  residuals?: { x: number; y: number; yHat: number }[]
  xDomain?: [number, number]
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart margin={{ top: 12, right: 18, bottom: 12, left: 0 }}>
        <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" />
        <XAxis dataKey="x" type="number" domain={xDomain} tick={{ fill: chart.tick, fontSize: 11 }} />
        <YAxis dataKey="y" type="number" tick={{ fill: chart.tick, fontSize: 11 }} width={42} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {residuals?.map((segment, index) => (
          <ReferenceLine
            key={`residual-${index}`}
            segment={[
              { x: segment.x, y: segment.y },
              { x: segment.x, y: segment.yHat },
            ]}
            stroke={segment.yHat >= segment.y ? chart.neg : chart.ok}
            strokeDasharray="3 4"
            strokeOpacity={0.52}
            strokeWidth={1.2}
            ifOverflow="visible"
          />
        ))}
        {lines.map((line) => (
          <Line
            key={line.name}
            data={line.data}
            type="monotone"
            dataKey="y"
            name={line.name}
            stroke={line.color}
            strokeDasharray={line.dash}
            dot={false}
            strokeWidth={2.4}
            isAnimationActive={false}
          />
        ))}
        <Scatter name="donnees" data={samples} fill={chart.sample} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function LossChart({ data, xKey = 'step' }: { data: HistoryRow[]; xKey?: string }) {
  const epsilon = 1e-6
  const values = data.map((row) => row.loss).filter((value) => Number.isFinite(value))
  const positiveValues = values.map((value) => Math.max(value, epsilon))
  const minPositive = Math.min(...positiveValues)
  const maxPositive = Math.max(...positiveValues)
  const useLogScale =
    positiveValues.length > 2 &&
    Number.isFinite(minPositive) &&
    Number.isFinite(maxPositive) &&
    maxPositive / Math.max(minPositive, epsilon) > 60
  const chartData = data.map((row) => ({ ...row, lossPlot: Math.max(row.loss, epsilon) }))
  const steps = data.map((row) => row[xKey]).filter((value) => Number.isFinite(value))
  const minStep = Math.min(...steps)
  const maxStep = Math.max(...steps)
  const xDomain: [number, number] =
    Number.isFinite(minStep) && Number.isFinite(maxStep)
      ? minStep === maxStep
        ? [minStep, minStep + 1]
        : [minStep, maxStep]
      : [0, 1]
  const yDomain: [number, number] | ['auto', 'auto'] = useLogScale
    ? [Math.max(epsilon, minPositive / 1.6), maxPositive * 1.25]
    : ['auto', 'auto']

  return (
    <div className="loss-chart-frame">
      {useLogScale && <span className="scale-badge">log scale</span>}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 12, right: 18, bottom: 12, left: 0 }}>
          <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" />
          <XAxis
            dataKey={xKey}
            type="number"
            domain={xDomain}
            tick={{ fill: chart.tick, fontSize: 11 }}
          />
          <YAxis
            dataKey="lossPlot"
            scale={useLogScale ? 'log' : 'auto'}
            domain={yDomain}
            tick={{ fill: chart.tick, fontSize: 11 }}
            tickFormatter={(value) => Number(value).toPrecision(useLogScale ? 2 : 3)}
            width={56}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(value: unknown, _name: unknown, props: any) => [
              Number(props?.payload?.loss ?? value).toPrecision(5),
              useLogScale ? 'loss (log scale)' : 'loss',
            ]}
          />
          <Line
            dataKey="lossPlot"
            name={useLogScale ? 'loss (log scale)' : 'loss'}
            stroke={chart.line}
            dot={false}
            strokeWidth={2.4}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function LabControls({
  running,
  onPlay,
  onPause,
  onStep,
  onReset,
  children,
}: {
  running: boolean
  onPlay: () => void
  onPause: () => void
  onStep: () => void
  onReset: () => void
  children: React.ReactNode
}) {
  return (
    <div className="lab-controls">
      <div className="lab-buttons">
        <button className="btn primary" disabled={running} onClick={onPlay}>
          <Icon name="play" />
          Play
        </button>
        <button className="btn" disabled={!running} onClick={onPause}>
          <Icon name="pause" />
          Pause
        </button>
        <button className="btn" onClick={onStep}>
          <Icon name="step" />
          Step
        </button>
        <button className="btn ghost" onClick={onReset}>
          <Icon name="reset" />
          Reset
        </button>
      </div>
      {children}
    </div>
  )
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label className="control-row">
      <span>{label}</span>
      <b>{Number.isInteger(value) ? value : value.toFixed(3)}</b>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

function Stepper({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <div className="stepper">
      <span>{label}</span>
      <div className="stepper-controls">
        <button type="button" disabled={value <= min} onClick={() => onChange(value - 1)}>
          &minus;
        </button>
        <b>{value}</b>
        <button type="button" disabled={value >= max} onClick={() => onChange(value + 1)}>
          +
        </button>
      </div>
    </div>
  )
}

function ExplanationList({ items }: { items: string[] }) {
  return (
    <div className="explain-list">
      {items.map((item, index) => (
        <div className="explain-step" key={item}>
          <span>{index + 1}</span>
          <p>{item}</p>
        </div>
      ))}
    </div>
  )
}

// One model covers the whole atelier: neurons === 1 is a plain line (editable
// w, b); neurons >= 2 is a ReLU hidden layer whose pieces sum into a curve.
interface LinModel {
  step: number
  neurons: number
  w: number // line: input -> output weight (neurons === 1)
  b: number // line: output bias (neurons === 1)
  w1: number[] // net: input -> hidden weights (neurons >= 2)
  b1: number[] // net: hidden biases
  w2: number[] // net: hidden -> output weights
  b2: number // net: output bias
  loss: number
}

function makeSamples(seed: number, noiseScale: number, curve: number): Point[] {
  const rand = rng(seed)
  return Array.from({ length: 28 }, (_, i) => {
    const x = -1.6 + (3.2 * i) / 27
    // curve === 0 keeps a pure line; a kink makes a line underfit and motivates neurons.
    const bend = curve * (Math.max(0, x + 0.5) - 2 * Math.max(0, x - 0.3))
    return { x, y: 1.2 * x - 0.2 + bend + dataNoise(rand, noiseScale) }
  })
}

function predict(m: LinModel, x: number): number {
  if (m.neurons === 1) return m.w * x + m.b
  let y = m.b2
  for (let i = 0; i < m.neurons; i += 1) {
    const z = m.w1[i] * x + m.b1[i]
    if (z > 0) y += m.w2[i] * z
  }
  return y
}

function modelLoss(m: LinModel, samples: Point[]): number {
  let s = 0
  for (const p of samples) {
    const e = predict(m, p.x) - p.y
    s += e * e
  }
  return s / samples.length
}

function initModel(neurons: number, seed: number, samples: Point[]): LinModel {
  if (neurons === 1) {
    const base: LinModel = { step: 0, neurons: 1, w: -1.15, b: 0.85, w1: [], b1: [], w2: [], b2: 0, loss: 0 }
    return { ...base, loss: modelLoss(base, samples) }
  }
  const rand = rng(seed * 131 + neurons)
  const w1: number[] = []
  const b1: number[] = []
  const w2: number[] = []
  for (let i = 0; i < neurons; i += 1) {
    const center = -0.9 + (1.8 * i) / Math.max(1, neurons - 1)
    const wi = 1.5
    w1.push(wi)
    b1.push(-wi * center)
    w2.push((rand() - 0.5) * 0.8)
  }
  const meanY = samples.reduce((sum, p) => sum + p.y, 0) / samples.length
  const base: LinModel = { step: 0, neurons, w: 0, b: 0, w1, b1, w2, b2: meanY, loss: 0 }
  return { ...base, loss: modelLoss(base, samples) }
}

function trainStep(m: LinModel, samples: Point[], lr: number): LinModel {
  const n = samples.length
  if (m.neurons === 1) {
    let dw = 0
    let db = 0
    for (const p of samples) {
      const e = m.w * p.x + m.b - p.y
      dw += 2 * e * p.x
      db += 2 * e
    }
    const w = m.w - lr * (dw / n)
    const b = m.b - lr * (db / n)
    const next: LinModel = { ...m, step: m.step + 1, w, b, loss: 0 }
    return { ...next, loss: modelLoss(next, samples) }
  }
  const gw1 = new Array<number>(m.neurons).fill(0)
  const gb1 = new Array<number>(m.neurons).fill(0)
  const gw2 = new Array<number>(m.neurons).fill(0)
  let gb2 = 0
  for (const p of samples) {
    let y = m.b2
    const z: number[] = []
    for (let i = 0; i < m.neurons; i += 1) {
      const zi = m.w1[i] * p.x + m.b1[i]
      z.push(zi)
      if (zi > 0) y += m.w2[i] * zi
    }
    const gy = (2 * (y - p.y)) / n
    gb2 += gy
    for (let i = 0; i < m.neurons; i += 1) {
      const h = z[i] > 0 ? z[i] : 0
      gw2[i] += gy * h
      const gz = z[i] > 0 ? gy * m.w2[i] : 0
      gw1[i] += gz * p.x
      gb1[i] += gz
    }
  }
  const next: LinModel = {
    ...m,
    step: m.step + 1,
    w1: m.w1.map((w, i) => w - lr * gw1[i]),
    b1: m.b1.map((b, i) => b - lr * gb1[i]),
    w2: m.w2.map((w, i) => w - lr * gw2[i]),
    b2: m.b2 - lr * gb2,
    loss: 0,
  }
  return { ...next, loss: modelLoss(next, samples) }
}

function lineGrad(m: LinModel, samples: Point[]) {
  let dw = 0
  let db = 0
  for (const p of samples) {
    const e = m.w * p.x + m.b - p.y
    dw += 2 * e * p.x
    db += 2 * e
  }
  return { dw: dw / samples.length, db: db / samples.length }
}

function probeActivations(m: LinModel, x: number): number[] {
  if (m.neurons === 1) return []
  return m.w1.map((w, i) => {
    const z = w * x + m.b1[i]
    return z > 0 ? z : 0
  })
}

// Per-parameter gradient, exactly the quantity each weight is nudged by during a
// step: next = value - lr * grad. Drives the "Pas" (step mechanics) view.
function modelGrad(m: LinModel, samples: Point[]): { name: string; value: number; grad: number }[] {
  const n = samples.length
  if (m.neurons === 1) {
    let dw = 0
    let db = 0
    for (const p of samples) {
      const e = m.w * p.x + m.b - p.y
      dw += 2 * e * p.x
      db += 2 * e
    }
    return [
      { name: 'w', value: m.w, grad: dw / n },
      { name: 'b', value: m.b, grad: db / n },
    ]
  }
  const gw1 = new Array<number>(m.neurons).fill(0)
  const gb1 = new Array<number>(m.neurons).fill(0)
  const gw2 = new Array<number>(m.neurons).fill(0)
  let gb2 = 0
  for (const p of samples) {
    let y = m.b2
    const z: number[] = []
    for (let i = 0; i < m.neurons; i += 1) {
      const zi = m.w1[i] * p.x + m.b1[i]
      z.push(zi)
      if (zi > 0) y += m.w2[i] * zi
    }
    const gy = (2 * (y - p.y)) / n
    gb2 += gy
    for (let i = 0; i < m.neurons; i += 1) {
      const h = z[i] > 0 ? z[i] : 0
      gw2[i] += gy * h
      const gz = z[i] > 0 ? gy * m.w2[i] : 0
      gw1[i] += gz * p.x
      gb1[i] += gz
    }
  }
  const rows: { name: string; value: number; grad: number }[] = []
  for (let i = 0; i < m.neurons; i += 1) {
    rows.push({ name: `v${i + 1}`, value: m.w2[i], grad: gw2[i] })
    rows.push({ name: `w${i + 1}`, value: m.w1[i], grad: gw1[i] })
    rows.push({ name: `b${i + 1}`, value: m.b1[i], grad: gb1[i] })
  }
  rows.push({ name: 'c', value: m.b2, grad: gb2 })
  return rows
}

function StepMechanics({ rows, lr }: { rows: { name: string; value: number; grad: number }[]; lr: number }) {
  const moves = rows.map((r) => lr * r.grad)
  const maxMove = Math.max(1e-6, ...moves.map((m) => Math.abs(m)))
  return (
    <div className="step-mech">
      <p className="step-mech-intro">
        Un pas de descente, parametre par parametre : <b>suivante = valeur &minus; lr &middot; gradient</b>. La fleche montre le deplacement
        choisi (sens oppose au gradient, longueur proportionnelle a lr &middot; gradient).
      </p>
      {rows.map((r, idx) => {
        const move = moves[idx]
        const next = r.value - move
        const frac = Math.min(1, Math.abs(move) / maxMove)
        const dir = next >= r.value ? 1 : -1
        const curPct = 50
        const nextPct = 50 + dir * frac * 40
        return (
          <div className="step-row" key={r.name}>
            <b className="step-name">{r.name}</b>
            <span className="step-calc">
              {r.value.toFixed(3)} &minus; {lr.toFixed(3)}&middot;<i style={{ color: '#7c9cff' }}>{r.grad.toFixed(3)}</i> = <em>{next.toFixed(3)}</em>
            </span>
            <div className="step-track">
              <span className="step-axis" />
              <span className="step-move" style={{ left: `${Math.min(curPct, nextPct)}%`, width: `${Math.abs(nextPct - curPct)}%` }} />
              <span className="step-dot cur" style={{ left: `${curPct}%` }} />
              <span className="step-dot next" style={{ left: `${nextPct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Tok({ c, children }: { c: string; children: ReactNode }) {
  return <b style={{ color: c, fontVariantNumeric: 'tabular-nums' }}>{children}</b>
}

interface OverlayData {
  residuals: { x: number; y: number; yHat: number; i: number }[]
  selected: number | null
  showResiduals: boolean
  showSquares: boolean
  showArrows: boolean
  showGhostPreds: boolean
  lossTotalSq: number
  onSelect: (i: number) => void
}

// Pixel-accurate overlay drawn inside the recharts svg via <Customized>, so the
// MSE squares are real squares and the gradient "pull" arrows scale with leverage.
function LinearOverlay(props: any) {
  const { xAxisMap, yAxisMap, overlay } = props as { xAxisMap: any; yAxisMap: any; overlay?: OverlayData }
  if (!xAxisMap || !yAxisMap || !overlay) return null
  const sx = xAxisMap[Object.keys(xAxisMap)[0]]?.scale
  const sy = yAxisMap[Object.keys(yAxisMap)[0]]?.scale
  if (!sx || !sy) return null
  const { residuals, selected, showResiduals, showSquares, showArrows, showGhostPreds, onSelect, lossTotalSq } = overlay
  const teal = '#4fd1c5'
  const indigo = '#7c9cff'
  const danger = '#f7768e'
  const ok = '#9ece6a'
  const warn = '#f6c177'
  const border = '#25304a'
  const chartW = typeof props.width === 'number' ? props.width : 99999
  return (
    <g>
      {showSquares &&
        residuals.map((r) => {
          const px = sx(r.x)
          const pY = sy(r.y)
          const pH = sy(r.yHat)
          const side = Math.abs(pY - pH)
          return (
            <rect key={`sq-${r.i}`} x={px} y={Math.min(pY, pH)} width={side} height={side} fill={danger} fillOpacity={0.12} stroke={danger} strokeOpacity={0.4} />
          )
        })}
      {showResiduals &&
        residuals.map((r) => {
          const px = sx(r.x)
          const pY = sy(r.y)
          const pH = sy(r.yHat)
          const isSel = selected === r.i
          return (
            <line
              key={`res-${r.i}`}
              x1={px}
              y1={pH}
              x2={px}
              y2={pY}
              stroke={r.yHat >= r.y ? danger : ok}
              strokeWidth={isSel ? 2.6 : 1.2}
              strokeDasharray="3 4"
              strokeOpacity={isSel ? 0.95 : 0.5}
            />
          )
        })}
      {showArrows &&
        residuals.map((r) => {
          const px = sx(r.x)
          const pY = sy(r.y)
          const pH = sy(r.yHat)
          const lever = 1 + Math.min(3, Math.abs(r.x) * 1.6)
          const dir = pY >= pH ? 1 : -1
          return (
            <g key={`arr-${r.i}`}>
              <line x1={px} y1={pH} x2={px} y2={pY} stroke={indigo} strokeWidth={lever} strokeOpacity={0.75} />
              <path d={`M ${px - 4} ${pY - dir * 6} L ${px + 4} ${pY - dir * 6} L ${px} ${pY} Z`} fill={indigo} opacity={0.85} />
            </g>
          )
        })}
      {showGhostPreds &&
        residuals.map((r) => <circle key={`gp-${r.i}`} cx={sx(r.x)} cy={sy(r.yHat)} r={3} fill={teal} fillOpacity={0.55} />)}
      {selected != null && residuals[selected] && (
        <circle cx={sx(residuals[selected].x)} cy={sy(residuals[selected].y)} r={7} fill="none" stroke={teal} strokeWidth={2} />
      )}
      {residuals.map((r) => (
        <circle key={`hit-${r.i}`} cx={sx(r.x)} cy={sy(r.y)} r={11} fill="transparent" style={{ cursor: 'pointer' }} onClick={() => onSelect(r.i)} />
      ))}
      {selected != null &&
        residuals[selected] &&
        ((sIdx: number) => {
          const r = residuals[sIdx]
          const px = sx(r.x)
          const py = sy(r.y)
          const e = r.yHat - r.y
          const e2 = e * e
          const pct = lossTotalSq > 0 ? (e2 / lossTotalSq) * 100 : 0
          const bw = 178
          const bh = 132
          let bx = px + 14
          let by = py - bh - 10
          if (by < 4) by = py + 14
          if (bx + bw > chartW - 4) bx = px - bw - 14
          if (bx < 4) bx = 4
          const rows: { k: string; v: string; c: string }[] = [
            { k: 'x', v: r.x.toFixed(3), c: '#e7edf7' },
            { k: 'y reel', v: r.y.toFixed(3), c: warn },
            { k: 'ŷ predit', v: r.yHat.toFixed(3), c: teal },
            { k: 'e = ŷ − y', v: e.toFixed(3), c: danger },
            { k: 'e² (aire)', v: e2.toFixed(3), c: '#e7edf7' },
            { k: 'part de loss', v: `${pct.toFixed(1)} %`, c: danger },
          ]
          return (
            <g>
              <line x1={px} y1={py} x2={bx < px ? bx + bw : bx} y2={by < py ? by + bh : by} stroke={border} strokeOpacity={0.7} />
              <rect x={bx} y={by} width={bw} height={bh} rx={8} fill="#1a2333" stroke={border} strokeWidth={1} />
              <text x={bx + 12} y={by + 21} fill={teal} fontSize={11} fontWeight={700}>
                point #{r.i}
              </text>
              <text x={bx + bw - 12} y={by + 22} fill="#9fb0c8" fontSize={15} textAnchor="end" style={{ cursor: 'pointer' }} onClick={() => onSelect(r.i)}>
                ×
              </text>
              {rows.map((row, idx) => (
                <g key={row.k}>
                  <text x={bx + 12} y={by + 44 + idx * 15} fill="#9fb0c8" fontSize={11}>
                    {row.k}
                  </text>
                  <text x={bx + bw - 12} y={by + 44 + idx * 15} fill={row.c} fontSize={11} fontWeight={700} textAnchor="end">
                    {row.v}
                  </text>
                </g>
              ))}
            </g>
          )
        })(selected)}
    </g>
  )
}

function LinearChart({
  samples,
  lines,
  overlay,
}: {
  samples: { x: number; y: number; i: number }[]
  lines: { name: string; data: Point[]; color: string; dash?: string }[]
  overlay: OverlayData
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart margin={{ top: 12, right: 18, bottom: 12, left: 0 }}>
        <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" />
        <XAxis dataKey="x" type="number" domain={[-1.9, 1.9]} tick={{ fill: chart.tick, fontSize: 11 }} />
        <YAxis dataKey="y" type="number" tick={{ fill: chart.tick, fontSize: 11 }} width={42} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {lines.map((l) => (
          <Line key={l.name} data={l.data} type="monotone" dataKey="y" name={l.name} stroke={l.color} strokeDasharray={l.dash} dot={false} strokeWidth={2.4} isAnimationActive={false} />
        ))}
        <Scatter name="donnees" data={samples} fill={chart.sample} isAnimationActive={false} />
        <Customized component={(p: any) => <LinearOverlay {...p} overlay={overlay} />} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

const PIPELINE_STAGES = [
  { key: 'data', label: 'Donnees' },
  { key: 'pred', label: 'Prediction' },
  { key: 'err', label: 'Erreur' },
  { key: 'loss', label: 'Loss' },
  { key: 'grad', label: 'Gradient' },
  { key: 'update', label: 'Update' },
]

function PipelineBar({ active, reached, onClick }: { active: number; reached: number; onClick: (i: number) => void }) {
  return (
    <div className="pipeline">
      {PIPELINE_STAGES.map((s, i) => (
        <Fragment key={s.key}>
          <button type="button" className={`pipeline-stage${active === i ? ' active' : ''}${i <= reached ? ' reached' : ''}`} onClick={() => onClick(i)}>
            <span className="pipeline-idx">{i + 1}</span>
            <span>{s.label}</span>
          </button>
          {i < PIPELINE_STAGES.length - 1 && <span className="pipeline-arrow">{'→'}</span>}
        </Fragment>
      ))}
    </div>
  )
}

const LINEAR_EXPERIMENTS: Experiment[] = [
  {
    id: 'curve',
    title: 'Vers une courbe',
    question: 'Donnees courbees + 1 seul neurone (droite) : que se passe-t-il ?',
    options: [
      { key: 'a', label: 'La droite suit la courbe' },
      { key: 'b', label: 'La droite sous-ajuste, des residus restent' },
    ],
    answerKey: 'b',
    reveal: 'Une droite ne peut pas plier. Monte les neurones a 2 ou 3 : chaque neurone ReLU ajoute un morceau lineaire, et leur somme epouse la courbe.',
    applyLabel: 'Courber les donnees',
  },
  {
    id: 'lr-high',
    title: 'Learning rate trop fort',
    question: 'Si on pousse le learning rate a 0.42, que fait la droite ?',
    options: [
      { key: 'a', label: 'Elle converge simplement plus vite' },
      { key: 'b', label: 'Elle oscille puis diverge' },
      { key: 'c', label: 'Rien ne change' },
    ],
    answerKey: 'b',
    reveal: 'Un pas trop grand depasse le minimum a chaque iteration : la loss oscille puis explose. Lance le Step apres avoir applique pour le voir.',
    applyLabel: 'Mettre lr = 0.42',
  },
  {
    id: 'bad-init',
    title: 'Mauvaise initialisation',
    question: 'On place la droite tres loin de la solution. Va-t-elle retrouver le bon ajustement ?',
    options: [
      { key: 'a', label: 'Oui, elle converge quand meme' },
      { key: 'b', label: 'Non, elle reste bloquee' },
    ],
    answerKey: 'a',
    reveal: 'La MSE est convexe pour une regression lineaire : un seul minimum global. D ou qu on parte, la descente y mene si le lr est raisonnable.',
    applyLabel: 'Eloigner la droite',
  },
  {
    id: 'outlier',
    title: 'Un point aberrant',
    question: 'On ajoute un point tres au-dessus des autres. Qu arrive-t-il a la droite ?',
    options: [
      { key: 'a', label: 'Elle ignore le point' },
      { key: 'b', label: 'Elle est fortement tiree vers lui' },
      { key: 'c', label: 'Elle arrete d apprendre' },
    ],
    answerKey: 'b',
    reveal: 'La MSE met l erreur au carre : un point lointain pese enormement. Selectionne-le pour voir sa part de la loss, souvent plus de 40 % a lui seul.',
    applyLabel: 'Ajouter un outlier',
  },
]

// One explanation card per pipeline stage, shown right under the stepper.
const STAGE_INFO = [
  {
    title: 'Les donnees',
    text: "On observe des couples (x, y) bruites : les points oranges. L'objectif est de trouver une regle qui predit y a partir de x. Pour l'instant, aucun modele n'existe : juste les faits a expliquer.",
  },
  {
    title: 'La prediction',
    text: "Avec 1 neurone, le modele propose ŷ = w·x + b : une droite. w regle la pente, b la hauteur. Pour chaque x observe, le petit point teal sur la droite est la valeur predite. Tu peux editer w et b directement dans la formule en bas.",
  },
  {
    title: "L'erreur",
    text: "Pour chaque point, e = ŷ − y mesure l'ecart vertical entre la prediction et la realite. Elle est signee : rouge quand le modele predit trop haut, verte quand il predit trop bas. Si la droite passait sur le point, e vaudrait 0.",
  },
  {
    title: 'La loss (MSE)',
    text: "Impossible d'optimiser 28 erreurs a la fois : on les resume en un seul nombre. La MSE est la moyenne des e². Le carre sert deux objectifs : les erreurs + et − ne s'annulent plus, et les gros ecarts pesent beaucoup plus fort. Chaque erreur devient litteralement l'aire d'un carre dessine sur le graphe.",
  },
  {
    title: 'Le gradient',
    text: "Le gradient repond a la question : si je bouge un peu w ou b, la loss monte ou descend ? Chaque point tire la droite vers lui (fleches indigo), proportionnellement a son erreur — et a sa distance a x = 0 pour la pente : un point eloigne a plus de levier.",
  },
  {
    title: 'La mise a jour',
    text: "On fait un pas dans le sens oppose au gradient : w ← w − lr·∂w, b ← b − lr·∂b. Le learning rate regle la taille du pas. La ligne verte en pointille montre ou sera le modele apres ce pas. Une iteration d'apprentissage = ce cycle complet, repete des dizaines de fois.",
  },
]
// Shown for the prediction stage when more than one neuron is active.
const PRED_MULTI =
  "Avec plusieurs neurones, chacun calcule sa propre droite wᵢ·x + bᵢ puis l'active (ReLU annule les valeurs negatives). La sortie additionne ces neurones ponderes par vᵢ, plus un biais c : ŷ = Σ vᵢ·relu(wᵢ·x + bᵢ) + c. En assemblant ces morceaux lineaires, le modele plie la droite en une courbe."
const ADVANCE_LABEL = ['→ Prediction', '→ Erreurs', '→ Loss', '→ Gradient', '→ Apercu du pas', 'Appliquer le pas ↻']
const FREE_HINT =
  "Mode libre : l'apprentissage tourne en continu. Clique un maillon de la chaine ci-dessus pour afficher son explication et sa couche visuelle, ou passe en mode Guide pour derouler les 6 etapes une par une."
// Dataset complexity follows model capacity: a line for 1 neuron, a curve beyond.
const ADAPTIVE_CURVE = [0, 0, 0.55, 0.95]
const SEED = 4

function LinearLab() {
  const [running, setRunning] = useState(false)
  const [lr, setLr] = useState(0.08)
  const [speed, setSpeed] = useState(8)
  const [noiseScale, setNoiseScale] = useState(0.18)
  const [neurons, setNeuronsRaw] = useState(1)
  // Adaptive dataset shape, unless an experiment forces a specific curvature.
  const [curveOverride, setCurveOverride] = useState<number | null>(null)
  const [outlier, setOutlier] = useState(false)
  const [mode, setMode] = useState<'free' | 'guided'>('free')
  const [stage, setStage] = useState(0) // guided: 0..5
  const [focus, setFocus] = useState(-1) // free: -1..5
  const [selected, setSelected] = useState<number | null>(null)
  const [rightView, setRightView] = useState<'loss' | 'landscape' | 'step'>('loss')

  const curve = curveOverride ?? ADAPTIVE_CURVE[neurons]
  const samples = useMemo(() => {
    const base = makeSamples(SEED, noiseScale, curve)
    return outlier ? [...base, { x: 1.05, y: 6.1 }] : base
  }, [noiseScale, curve, outlier])

  const setNeurons = (n: number) => {
    setCurveOverride(null)
    setNeuronsRaw(n)
  }

  const initialModel = useMemo<LinModel>(() => initModel(neurons, SEED, samples), [neurons, samples])
  const [model, setModel] = useState(initialModel)
  const [history, setHistory] = useState<HistoryRow[]>([{ step: 0, loss: initialModel.loss, w: initialModel.w, b: initialModel.b }])

  const reset = () => {
    setRunning(false)
    setModel(initialModel)
    setHistory([{ step: 0, loss: initialModel.loss, w: initialModel.w, b: initialModel.b }])
    if (mode === 'guided') setStage(0)
  }

  useEffect(reset, [initialModel])

  const stepOnce = () => {
    setModel((current) => {
      const next = trainStep(current, samples, lr)
      setHistory((rows) => [...rows, { step: next.step, loss: next.loss, w: next.w, b: next.b }])
      return next
    })
  }

  useLoop(running && mode === 'free', Math.max(16, 260 - speed * 22), stepOnce)

  // Editing w/b in the formula rewrites the current line in place (neurons === 1).
  const setLine = (w: number, b: number) => {
    setRunning(false)
    const base: LinModel = { ...model, step: 0, neurons: 1, w, b, w1: [], b1: [], w2: [], b2: 0, loss: 0 }
    const m: LinModel = { ...base, loss: modelLoss(base, samples) }
    setModel(m)
    setHistory([{ step: 0, loss: m.loss, w, b }])
  }

  const switchMode = (m: 'free' | 'guided') => {
    setRunning(false)
    setMode(m)
    if (m === 'guided') setStage(0)
    else setFocus(-1)
  }

  const guided = mode === 'guided'
  const advance = () => {
    if (stage < 5) {
      setStage(stage + 1)
      return
    }
    stepOnce()
    setStage(1)
  }

  const onStageClick = (i: number) => {
    if (guided) setStage(Math.max(0, Math.min(5, i)))
    else setFocus(focus === i ? -1 : i)
  }

  const applyExperiment = (id: string) => {
    if (id === 'curve') {
      setNeuronsRaw(1)
      setCurveOverride(0.85)
      switchMode('free')
    } else if (id === 'lr-high') {
      setLr(0.42)
      switchMode('free')
    } else if (id === 'bad-init') {
      switchMode('free')
      if (neurons === 1) setLine(2.8, -1.6)
      else reset()
    } else if (id === 'outlier') {
      setOutlier(true)
      switchMode('free')
    }
  }

  const preview = useMemo(() => trainStep(model, samples, lr), [model, samples, lr])
  const grad = useMemo(() => lineGrad(model, samples), [model, samples])
  const wNext = preview.w
  const bNext = preview.b
  const paramCount = neurons === 1 ? 2 : neurons * 3 + 1
  const canLandscape = neurons === 1
  const effectiveView: 'loss' | 'landscape' | 'step' = rightView === 'landscape' && !canLandscape ? 'loss' : rightView
  const gradRows = useMemo(() => modelGrad(model, samples), [model, samples])

  const showGhostPreds = guided ? stage >= 1 : false
  const showResiduals = guided ? stage >= 2 : true
  const showSquares = guided ? stage >= 3 : focus === 3
  const showArrows = guided ? stage >= 4 : focus === 4
  const showNextLine = guided ? stage >= 5 : false
  const activeStage = guided ? stage : focus

  const gridX = lineGrid(-1.9, 1.9, neurons === 1 ? 60 : 160)
  const line = gridX.map((x) => ({ x, y: predict(model, x) }))
  const startLine = gridX.map((x) => ({ x, y: predict(initialModel, x) }))
  const nextLine = gridX.map((x) => ({ x, y: predict(preview, x) }))
  const indexed = samples.map((p, i) => ({ ...p, i }))
  const residuals = samples.map((p, i) => ({ x: p.x, y: p.y, yHat: predict(model, p.x), i }))
  const acts = probeActivations(model, 0.6)

  // Guided stage 0 shows the bare dataset: no model line at all yet.
  const lines: { name: string; data: Point[]; color: string; dash?: string }[] = []
  if (!guided) lines.push({ name: 'depart', data: startLine, color: chart.line2, dash: '5 5' })
  if (!guided || stage >= 1) lines.push({ name: 'prediction', data: line, color: chart.line })
  if (showNextLine) lines.push({ name: 'prochaine etape', data: nextLine, color: chart.ok, dash: '4 4' })

  const overlay: OverlayData = {
    residuals,
    selected,
    showResiduals,
    showSquares,
    showArrows,
    showGhostPreds,
    lossTotalSq: model.loss * samples.length,
    onSelect: (i: number) => setSelected((p) => (p === i ? null : i)),
  }

  const sel = selected != null && selected < samples.length ? samples[selected] : null
  const selPred = sel ? predict(model, sel.x) : 0
  const selErr = sel ? selPred - sel.y : 0
  const sumSq = model.loss * samples.length
  const selContrib = sel && sumSq > 0 ? (selErr * selErr) / sumSq : 0

  const tealC = chart.line
  const dataC = chart.sample
  const errC = chart.neg
  const lossC = chart.ok
  const gradC = chart.line2

  return (
    <div className="lesson-page">
      <LessonHeader eyebrow="Atelier 01" title="De la droite au reseau">
        Un parcours en 6 etapes : donnees, prediction, erreur, loss, gradient, mise a jour.
        Le mode Guide les deroule une par une, avec une explication a chaque etape. Edite la
        droite dans la formule, puis monte le nombre de neurones : les donnees s adaptent et
        la droite devient courbe.
      </LessonHeader>

      <div className="linear-layout">
        {/* Top block: actions row + settings row, always visible. */}
        <div className="linear-controls">
          <div className="linear-controlstrip">
            <div className="segmented">
              <button className={mode === 'free' ? 'active' : ''} onClick={() => switchMode('free')}>
                Libre
              </button>
              <button className={mode === 'guided' ? 'active' : ''} onClick={() => switchMode('guided')}>
                Guide
              </button>
            </div>
            {guided ? (
              <button className="btn primary guided-advance" onClick={advance}>
                {ADVANCE_LABEL[stage]}
              </button>
            ) : (
              <>
                <button className="btn primary" disabled={running} onClick={() => setRunning(true)}>
                  <Icon name="play" />
                  Play
                </button>
                <button className="btn" disabled={!running} onClick={() => setRunning(false)}>
                  <Icon name="pause" />
                  Pause
                </button>
                <button className="btn" onClick={stepOnce}>
                  <Icon name="step" />
                  Step
                </button>
              </>
            )}
            <button className="btn ghost" onClick={reset}>
              <Icon name="reset" />
              Reset
            </button>
            <span className="spacer" />
            <span className="strip-stat">
              step <b>{model.step}</b>
            </span>
            <span className="strip-stat">
              loss <b>{model.loss.toFixed(4)}</b>
            </span>
          </div>
          <div className="linear-settingsrow">
            <Stepper label="neurones" min={1} max={3} value={neurons} onChange={setNeurons} />
            <div className="setting-slider">
              <Slider label="learning rate" min={0.001} max={0.5} step={0.001} value={lr} onChange={setLr} />
            </div>
            <div className="setting-slider">
              <Slider label="bruit donnees" min={0} max={1.2} step={0.02} value={noiseScale} onChange={setNoiseScale} />
            </div>
            {!guided && (
              <div className="setting-slider">
                <Slider label="vitesse" min={1} max={10} step={1} value={speed} onChange={setSpeed} />
              </div>
            )}
            {outlier && (
              <button className="btn ghost" onClick={() => setOutlier(false)}>
                retirer l outlier
              </button>
            )}
          </div>
        </div>

        <PipelineBar active={activeStage} reached={guided ? stage : 5} onClick={onStageClick} />

        {/* Contextual explanation for the active stage. */}
        <div className="stage-info">
          {activeStage >= 0 ? (
            <>
              <span className="stage-info-idx">{activeStage + 1}</span>
              <div>
                <b>{STAGE_INFO[activeStage].title}</b>
                <p>{activeStage === 1 && neurons > 1 ? PRED_MULTI : STAGE_INFO[activeStage].text}</p>
              </div>
            </>
          ) : (
            <p className="stage-info-hint">{FREE_HINT}</p>
          )}
        </div>

        <span className="row-label">Le modele &mdash; deux vues equivalentes</span>
        <div className="linear-row">
          <section className="panel chart-panel">
            <div className="panel-header">
              <span className="panel-title">Donnees et prediction</span>
              <span className="panel-title">{neurons === 1 ? 'droite' : `${neurons} morceaux ReLU`}</span>
            </div>
            <div className="panel-body">
              <LinearChart samples={indexed} lines={lines} overlay={overlay} />
            </div>
          </section>

          <section className="panel net-panel">
            <div className="panel-header">
              <span className="panel-title">Equivalent neuronal</span>
              <span className="panel-title">{neurons === 1 ? '1 neurone' : `${neurons} neurones`}</span>
            </div>
            <div className="panel-body">
              <NetworkDiagram
                neurons={neurons}
                w={model.w}
                b={model.b}
                w1={model.w1}
                b1={model.b1}
                w2={model.w2}
                b2={model.b2}
                activations={acts}
              />
            </div>
          </section>
        </div>

        <span className="row-label">Le calcul &mdash; formule et convergence</span>
        <div className="linear-row">
          <section className="panel">
            <div className="panel-header">
              <span className="panel-title">Formule vivante</span>
              {activeStage >= 0 && <span className="panel-title">etape {activeStage + 1}/6</span>}
            </div>
            <div className="formula-panel">
              <div className={`formula-line${activeStage === 1 ? ' active' : ''}`}>
                {neurons === 1 ? (
                  <>
                    <code className="formula-inline">
                      <Tok c={tealC}>y&#770;</Tok> =
                      <span className="tok-field">
                        <em>w</em>
                        <input
                          className="tok-input"
                          type="number"
                          step={0.05}
                          value={round(model.w, 3)}
                          style={{ color: tealC }}
                          onChange={(e) => {
                            const v = Number(e.target.value)
                            if (Number.isFinite(v)) setLine(v, model.b)
                          }}
                        />
                      </span>
                      &middot;x +
                      <span className="tok-field">
                        <em>b</em>
                        <input
                          className="tok-input"
                          type="number"
                          step={0.05}
                          value={round(model.b, 3)}
                          style={{ color: tealC }}
                          onChange={(e) => {
                            const v = Number(e.target.value)
                            if (Number.isFinite(v)) setLine(model.w, v)
                          }}
                        />
                      </span>
                    </code>
                    <small>edite w et b : la droite et son neurone bougent ensemble</small>
                  </>
                ) : (
                  <>
                    <div className="formula-sum">
                      <Tok c={tealC}>y&#770;</Tok> =
                      <span className="big-sigma" style={{ fontSize: neurons >= 3 ? 42 : 32 }}>
                        &Sigma;
                      </span>
                      <div className="sum-terms">
                        {model.w2.map((v, i) => (
                          <code key={i}>
                            <Tok c={tealC}>{v.toFixed(2)}</Tok>&middot;relu(<Tok c={tealC}>{model.w1[i].toFixed(2)}</Tok>&middot;x{model.b1[i] >= 0 ? ' + ' : ' − '}
                            <Tok c={tealC}>{Math.abs(model.b1[i]).toFixed(2)}</Tok>)
                          </code>
                        ))}
                      </div>
                      <span className="sum-tail">
                        + <Tok c={tealC}>{model.b2.toFixed(2)}</Tok>
                      </span>
                    </div>
                    <small>{neurons} neurones : une ligne = un morceau lineaire (ReLU)</small>
                  </>
                )}
                {sel && (
                  <small>
                    <Tok c={tealC}>y&#770;</Tok>({sel.x.toFixed(2)}) = {selPred.toFixed(2)}
                  </small>
                )}
              </div>
              <div className={`formula-line${activeStage === 2 ? ' active' : ''}`}>
                <code>
                  <Tok c={errC}>e</Tok> = <Tok c={tealC}>y&#770;</Tok> &minus; <Tok c={dataC}>y</Tok>
                </code>
                {sel && (
                  <small>
                    <Tok c={errC}>e</Tok> = {selPred.toFixed(2)} &minus; {sel.y.toFixed(2)} = {selErr.toFixed(2)}
                  </small>
                )}
              </div>
              <div className={`formula-line${activeStage === 3 ? ' active' : ''}`}>
                <code>
                  <Tok c={lossC}>MSE</Tok> = moyenne(<Tok c={errC}>e</Tok>&sup2;) = <Tok c={lossC}>{model.loss.toFixed(4)}</Tok>
                </code>
                {sel && (
                  <small>
                    ce point pese <Tok c={errC}>{(selContrib * 100).toFixed(1)}%</Tok> de la loss
                  </small>
                )}
              </div>
              <div className={`formula-line${activeStage === 4 ? ' active' : ''}`}>
                {neurons === 1 ? (
                  <>
                    <code>
                      &part;L/&part;<Tok c={tealC}>w</Tok> = moy(2&middot;<Tok c={errC}>e</Tok>&middot;x) = <Tok c={gradC}>{grad.dw.toFixed(3)}</Tok>
                    </code>
                    <code>
                      &part;L/&part;<Tok c={tealC}>b</Tok> = moy(2&middot;<Tok c={errC}>e</Tok>) = <Tok c={gradC}>{grad.db.toFixed(3)}</Tok>
                    </code>
                  </>
                ) : (
                  <>
                    <code>
                      Backprop : &part;L/&part;poids pour les <Tok c={gradC}>{paramCount}</Tok> poids
                    </code>
                    <small>chaque neurone recoit sa part de l erreur</small>
                  </>
                )}
              </div>
              <div className={`formula-line${activeStage === 5 ? ' active' : ''}`}>
                {neurons === 1 ? (
                  <>
                    <code>
                      <Tok c={tealC}>w</Tok> &larr; {model.w.toFixed(3)} &minus; {lr.toFixed(3)}&middot;<Tok c={gradC}>{grad.dw.toFixed(3)}</Tok> = <Tok c={tealC}>{wNext.toFixed(3)}</Tok>
                    </code>
                    <code>
                      <Tok c={tealC}>b</Tok> &larr; {model.b.toFixed(3)} &minus; {lr.toFixed(3)}&middot;<Tok c={gradC}>{grad.db.toFixed(3)}</Tok> = <Tok c={tealC}>{bNext.toFixed(3)}</Tok>
                    </code>
                  </>
                ) : (
                  <>
                    <code>poids &larr; poids &minus; lr&middot;gradient</code>
                    <small>
                      loss {model.loss.toFixed(4)} &rarr; {preview.loss.toFixed(4)}
                    </small>
                  </>
                )}
              </div>
            </div>
          </section>

          <section className="panel chart-panel short">
            <div className="panel-header">
              <span className="panel-title">
                {effectiveView === 'loss' ? 'Loss dans le temps' : effectiveView === 'landscape' ? 'Paysage de loss (w, b)' : 'Mecanique du pas'}
              </span>
              <div className="segmented">
                <button className={effectiveView === 'loss' ? 'active' : ''} onClick={() => setRightView('loss')}>
                  Loss
                </button>
                <button className={effectiveView === 'step' ? 'active' : ''} onClick={() => setRightView('step')}>
                  Pas
                </button>
                <button
                  className={effectiveView === 'landscape' ? 'active' : ''}
                  disabled={!canLandscape}
                  title={canLandscape ? undefined : 'disponible pour la droite (2 parametres)'}
                  onClick={() => setRightView('landscape')}
                >
                  Paysage
                </button>
              </div>
            </div>
            <div className="panel-body">
              {effectiveView === 'loss' ? (
                <LossChart data={history} />
              ) : effectiveView === 'step' ? (
                <StepMechanics rows={gradRows} lr={lr} />
              ) : (
                <LossLandscape
                  samples={samples}
                  w={model.w}
                  b={model.b}
                  trajectory={history.map((h) => ({ w: h.w, b: h.b }))}
                  next={{ w: preview.w, b: preview.b }}
                />
              )}
            </div>
          </section>
        </div>

        <span className="row-label">Predis puis observe</span>
        <section className="panel">
          <ExperimentCards experiments={LINEAR_EXPERIMENTS} onApply={applyExperiment} />
        </section>
      </div>
    </div>
  )
}

interface QuadModel {
  step: number
  w1: number[]
  b1: number[]
  w2: number[]
  b2: number
  mw1: number[]
  vw1: number[]
  mb1: number[]
  vb1: number[]
  mw2: number[]
  vw2: number[]
  mb2: number
  vb2: number
  loss: number
}

function makeQuadraticSamples(seed: number, noiseScale: number) {
  const rand = rng(seed)
  return Array.from({ length: 46 }, (_, i) => {
    const x = -1.35 + (2.7 * i) / 45
    return { x, y: 0.85 * x * x - 0.25 * x - 0.55 + dataNoise(rand, noiseScale) }
  })
}

function initQuad(hidden: number, seed: number, samples: Point[]): QuadModel {
  const rand = rng(seed * 97 + hidden)
  const centers = Array.from({ length: hidden }, (_, i) => -1.25 + (2.5 * i) / Math.max(1, hidden - 1))
  const meanY = samples.reduce((sum, p) => sum + p.y, 0) / samples.length
  const w1 = centers.map(() => 1.65 + rand() * 1.2)
  const zeros = Array.from({ length: hidden }, () => 0)
  const model: QuadModel = {
    step: 0,
    w1,
    b1: centers.map((center, i) => -w1[i] * center + noise(rand, 0.04)),
    w2: Array.from({ length: hidden }, () => (rand() - 0.5) * 0.28),
    b2: meanY,
    mw1: [...zeros],
    vw1: [...zeros],
    mb1: [...zeros],
    vb1: [...zeros],
    mw2: [...zeros],
    vw2: [...zeros],
    mb2: 0,
    vb2: 0,
    loss: 0,
  }
  return { ...model, loss: quadLoss(model, samples) }
}

function quadForward(model: QuadModel, x: number) {
  const hidden = model.w1.map((w, i) => Math.tanh(w * x + model.b1[i]))
  const y = hidden.reduce((sum, h, i) => sum + h * model.w2[i], model.b2)
  return { hidden, y }
}

function quadLoss(model: QuadModel, samples: Point[]) {
  return samples.reduce((sum, p) => sum + (quadForward(model, p.x).y - p.y) ** 2, 0) / samples.length
}

function trainQuad(model: QuadModel, samples: Point[], lr: number): QuadModel {
  const gw1 = model.w1.map(() => 0)
  const gb1 = model.b1.map(() => 0)
  const gw2 = model.w2.map(() => 0)
  let gb2 = 0

  for (const p of samples) {
    const { hidden, y } = quadForward(model, p.x)
    const gy = (2 * (y - p.y)) / samples.length
    gb2 += gy
    for (let i = 0; i < hidden.length; i += 1) {
      gw2[i] += gy * hidden[i]
      const gz = gy * model.w2[i] * (1 - hidden[i] * hidden[i])
      gw1[i] += gz * p.x
      gb1[i] += gz
    }
  }

  const beta1 = 0.9
  const beta2 = 0.999
  const eps = 1e-8
  const t = model.step + 1

  const adam = (value: number, grad: number, m: number, v: number) => {
    const nextM = beta1 * m + (1 - beta1) * grad
    const nextV = beta2 * v + (1 - beta2) * grad * grad
    const mHat = nextM / (1 - beta1 ** t)
    const vHat = nextV / (1 - beta2 ** t)
    return {
      value: value - (lr * mHat) / (Math.sqrt(vHat) + eps),
      m: nextM,
      v: nextV,
    }
  }

  const w1Updates = model.w1.map((w, i) => adam(w, gw1[i], model.mw1[i], model.vw1[i]))
  const b1Updates = model.b1.map((b, i) => adam(b, gb1[i], model.mb1[i], model.vb1[i]))
  const w2Updates = model.w2.map((w, i) => adam(w, gw2[i], model.mw2[i], model.vw2[i]))
  const b2Update = adam(model.b2, gb2, model.mb2, model.vb2)

  const next: QuadModel = {
    step: model.step + 1,
    w1: w1Updates.map((u) => u.value),
    b1: b1Updates.map((u) => u.value),
    w2: w2Updates.map((u) => u.value),
    b2: b2Update.value,
    mw1: w1Updates.map((u) => u.m),
    vw1: w1Updates.map((u) => u.v),
    mb1: b1Updates.map((u) => u.m),
    vb1: b1Updates.map((u) => u.v),
    mw2: w2Updates.map((u) => u.m),
    vw2: w2Updates.map((u) => u.v),
    mb2: b2Update.m,
    vb2: b2Update.v,
    loss: 0,
  }
  return { ...next, loss: quadLoss(next, samples) }
}

function WeightBars({ model }: { model: QuadModel }) {
  const values = [...model.w1.map((v, i) => ({ label: `x->h${i + 1}`, value: v })), ...model.w2.map((v, i) => ({ label: `h${i + 1}->y`, value: v }))]
  const max = Math.max(0.1, ...values.map((v) => Math.abs(v.value)))
  return (
    <div className="weight-bars">
      {values.map(({ label, value }) => (
        <div className="weight-row" key={label}>
          <span>{label}</span>
          <i><b style={{ width: `${Math.max(4, (Math.abs(value) / max) * 100)}%`, background: value >= 0 ? chart.line : chart.neg }} /></i>
          <em>{value.toFixed(2)}</em>
        </div>
      ))}
    </div>
  )
}

function TinyNetworkView({ model }: { model: QuadModel }) {
  const probe = [-1, -0.25, 0.5, 1]
  return (
    <div className="network-live">
      {probe.map((x) => {
        const out = quadForward(model, x)
        return (
          <div className="probe-row" key={x}>
            <b>x={x}</b>
            <span>y={out.y.toFixed(2)}</span>
            <div>
              {out.hidden.map((value, index) => (
                <i
                  key={index}
                  title={`h${index + 1}: ${value.toFixed(3)}`}
                  style={{
                    opacity: 0.2 + Math.abs(value) * 0.8,
                    background: value >= 0 ? chart.line : chart.neg,
                  }}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function QuadraticLab() {
  const [running, setRunning] = useState(false)
  const [lr, setLr] = useState(0.018)
  const [speed, setSpeed] = useState(8)
  const [seed, setSeed] = useState(7)
  const [hidden, setHidden] = useState(6)
  const [noiseScale, setNoiseScale] = useState(0.035)
  const samples = useMemo(() => makeQuadraticSamples(seed, noiseScale), [noiseScale, seed])
  const initialModel = useMemo(() => initQuad(hidden, seed, samples), [hidden, samples, seed])
  const [model, setModel] = useState(initialModel)
  const [history, setHistory] = useState<HistoryRow[]>([{ step: 0, loss: initialModel.loss }])

  const reset = () => {
    setRunning(false)
    setModel(initialModel)
    setHistory([{ step: 0, loss: initialModel.loss }])
  }

  useEffect(reset, [initialModel])

  const stepOnce = () => {
    setModel((current) => {
      const next = trainQuad(current, samples, lr)
      setHistory((rows) => [...rows, { step: next.step, loss: next.loss }])
      return next
    })
  }

  useLoop(running, Math.max(16, 260 - speed * 22), stepOnce)

  const prediction = lineGrid(-1.45, 1.45, 90).map((x) => ({ x, y: quadForward(model, x).y }))
  const residuals = samples.map((p) => ({ x: p.x, y: p.y, yHat: quadForward(model, p.x).y }))

  return (
    <div className="lesson-page">
      <LessonHeader eyebrow="Atelier 02" title="Reseau quadratique en apprentissage live">
        Cette fois la courbe n'est pas une trace rejouee: a chaque iteration, le
        reseau fait un forward pass, calcule le gradient par backpropagation, puis
        modifie ses poids. Les barres et activations changent avec la prediction.
      </LessonHeader>

      <div className="lesson-grid">
        <section className="panel lesson-main">
          <div className="panel-header">
            <span className="panel-title">Approximation 2D vivante</span>
            <span className="panel-title">step {model.step} - loss {model.loss.toFixed(5)}</span>
          </div>
          <div className="panel-body">
            <PointLineChart
              samples={samples}
              residuals={residuals}
              lines={[{ name: 'prediction', data: prediction, color: chart.line }]}
              xDomain={[-1.5, 1.5]}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Loss en temps reel</span>
          </div>
          <div className="panel-body">
            <LossChart data={history} />
          </div>
        </section>

        <section className="panel lesson-notes">
          <div className="panel-header">
            <span className="panel-title">Boucle et parametres</span>
          </div>
          <LabControls running={running} onPlay={() => setRunning(true)} onPause={() => setRunning(false)} onStep={stepOnce} onReset={reset}>
            <Slider label="learning rate" min={0.001} max={0.08} step={0.001} value={lr} onChange={setLr} />
            <Slider label="vitesse" min={1} max={10} step={1} value={speed} onChange={setSpeed} />
            <Slider label="neurones caches" min={3} max={12} step={1} value={hidden} onChange={setHidden} />
            <Slider label="bruit donnees" min={0} max={0.9} step={0.01} value={noiseScale} onChange={setNoiseScale} />
            <Slider label="seed" min={1} max={30} step={1} value={seed} onChange={setSeed} />
          </LabControls>
        </section>

        <section className="panel lesson-metrics">
          <div className="panel-header">
            <span className="panel-title">Reseau en train de bouger</span>
          </div>
          <TinyNetworkView model={model} />
          <WeightBars model={model} />
        </section>
      </div>
    </div>
  )
}

interface NeatAgent {
  id: number
  x: number
  y: number
  fitness: number
  species: number
  complexity: number
}

function makePopulation(popSize: number, seed: number): NeatAgent[] {
  const rand = rng(seed)
  return Array.from({ length: popSize }, (_, id) => {
    const x = rand() * 2 - 1
    const y = rand() * 2 - 1
    return {
      id,
      x,
      y,
      fitness: 0,
      species: 1 + Math.floor(rand() * 3),
      complexity: 4 + Math.floor(rand() * 4),
    }
  })
}

function scoreAgent(a: NeatAgent) {
  const target = Math.sin(a.x * 3) * Math.cos(a.y * 2)
  return Math.max(0, 3 - Math.abs(target - (a.x * a.y + 0.35 * Math.sin(a.complexity))))
}

function evolvePopulation(pop: NeatAgent[], mutation: number, seed: number, gen: number) {
  const rand = rng(seed * 101 + gen * 17)
  const ranked = pop.map((a) => ({ ...a, fitness: scoreAgent(a) })).sort((a, b) => b.fitness - a.fitness)
  const elites = ranked.slice(0, Math.max(2, Math.floor(pop.length * 0.18)))
  const next: NeatAgent[] = elites.slice(0, 2).map((a, id) => ({ ...a, id }))
  while (next.length < pop.length) {
    const parent = elites[Math.floor(rand() * elites.length)]
    const structural = rand() < mutation
    next.push({
      id: next.length,
      x: parent.x + noise(rand, 0.16),
      y: parent.y + noise(rand, 0.16),
      fitness: 0,
      species: structural ? 1 + Math.floor(rand() * 5) : parent.species,
      complexity: Math.max(3, Math.min(22, parent.complexity + (structural ? 1 : 0) + Math.floor(noise(rand, 0.9)))),
    })
  }
  return next
}

function NeatCloud({ agents }: { agents: NeatAgent[] }) {
  const maxFitness = Math.max(0.1, ...agents.map((a) => a.fitness))
  return (
    <svg className="neat-cloud" viewBox="0 0 420 260">
      {agents.map((a) => (
        <circle
          key={a.id}
          cx={40 + ((a.x + 1.5) / 3) * 340}
          cy={220 - ((a.y + 1.5) / 3) * 180}
          r={4 + (a.fitness / maxFitness) * 10}
          fill={a.species % 2 ? chart.line : chart.line2}
          opacity={0.28 + (a.fitness / maxFitness) * 0.65}
          stroke={a.fitness === maxFitness ? chart.ok : 'transparent'}
          strokeWidth={2}
        />
      ))}
    </svg>
  )
}

function NeatLab() {
  const [running, setRunning] = useState(false)
  const [seed, setSeed] = useState(11)
  const [popSize, setPopSize] = useState(44)
  const [mutation, setMutation] = useState(0.18)
  const [speed, setSpeed] = useState(6)
  const [gen, setGen] = useState(0)
  const [agents, setAgents] = useState(() => makePopulation(popSize, seed))
  const [history, setHistory] = useState<HistoryRow[]>([])

  const reset = () => {
    const pop = makePopulation(popSize, seed)
    setRunning(false)
    setGen(0)
    setAgents(pop)
    setHistory([])
  }

  useEffect(reset, [popSize, seed])

  const stepOnce = () => {
    setAgents((current) => {
      const evaluated = current.map((a) => ({ ...a, fitness: scoreAgent(a) }))
      const max = Math.max(...evaluated.map((a) => a.fitness))
      const mean = evaluated.reduce((sum, a) => sum + a.fitness, 0) / evaluated.length
      const complexity = evaluated.reduce((sum, a) => sum + a.complexity, 0) / evaluated.length
      const species = new Set(evaluated.map((a) => a.species)).size
      const nextGen = gen + 1
      setGen(nextGen)
      setHistory((rows) => [...rows, { step: nextGen, loss: round(3 - max), fitnessMax: max, fitnessMean: mean, complexity, species }])
      return evolvePopulation(evaluated, mutation, seed, nextGen)
    })
  }

  useLoop(running, Math.max(40, 420 - speed * 34), stepOnce)
  const evaluated = agents.map((a) => ({ ...a, fitness: scoreAgent(a) }))
  const best = evaluated.reduce((a, b) => (a.fitness > b.fitness ? a : b), evaluated[0])

  return (
    <div className="lesson-page">
      <LessonHeader eyebrow="Atelier 03" title="Mini-NEAT interactif">
        Cette demo compacte evolue une population en direct: selection des meilleurs,
        mutations de poids et petites mutations structurelles. Le labo Flappy reste
        l'application complete juste apres.
      </LessonHeader>

      <div className="lesson-grid">
        <section className="panel lesson-main">
          <div className="panel-header">
            <span className="panel-title">Population en evolution</span>
            <span className="panel-title">generation {gen}</span>
          </div>
          <div className="panel-body">
            <NeatCloud agents={evaluated} />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Erreur du meilleur</span>
          </div>
          <div className="panel-body">
            <LossChart data={history.length ? history : [{ step: 0, loss: 3 }]} />
          </div>
        </section>

        <section className="panel lesson-notes">
          <div className="panel-header">
            <span className="panel-title">Parametres evolution</span>
          </div>
          <LabControls running={running} onPlay={() => setRunning(true)} onPause={() => setRunning(false)} onStep={stepOnce} onReset={reset}>
            <Slider label="population" min={16} max={100} step={2} value={popSize} onChange={setPopSize} />
            <Slider label="mutation structurelle" min={0.02} max={0.5} step={0.01} value={mutation} onChange={setMutation} />
            <Slider label="vitesse" min={1} max={10} step={1} value={speed} onChange={setSpeed} />
            <Slider label="seed" min={1} max={30} step={1} value={seed} onChange={setSeed} />
          </LabControls>
        </section>

        <section className="panel lesson-metrics">
          <div className="panel-header">
            <span className="panel-title">Meilleur genome jouet</span>
          </div>
          <div className="metric-grid">
            <div><small>fitness</small><b>{best.fitness.toFixed(3)}</b></div>
            <div><small>espece</small><b>{best.species}</b></div>
            <div><small>complexite</small><b>{best.complexity}</b></div>
            <div><small>generation</small><b>{gen}</b></div>
          </div>
          <ExplanationList items={[
            "Chaque point est un genome candidat; sa taille indique sa fitness.",
            "Les meilleurs produisent la generation suivante avec mutations.",
            "La mutation structurelle augmente parfois la complexite, comme l'ajout de noeuds ou connexions dans NEAT.",
          ]} />
        </section>
      </div>
    </div>
  )
}

export function LessonLabs({ active }: { active: LessonId }) {
  const lab = useMemo(() => {
    if (active === 'linear') return <LinearLab />
    if (active === 'quadratic') return <QuadraticLab />
    if (active === 'neat') return <NeatLab />
    return null
  }, [active])

  return lab
}
