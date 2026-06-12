// ─── NetworkDiagram ───────────────────────────────────────────────────────────
// Pure SVG neural-network diagram.
// neurons === 1  →  single input→output edge  (linear y = w·x + b)
// neurons >= 2  →  input → hidden ReLU layer → output  (piecewise-linear)

// ─── Palette ─────────────────────────────────────────────────────────────────

const C_NODE_FILL    = '#1a2333'
const C_INPUT_STROKE = '#7c9cff'
const C_HIDDEN_STROKE= '#f6c177'
const C_OUTPUT_STROKE= '#4fd1c5'
const C_TEXT         = '#e7edf7'
const C_DIM          = '#9fb0c8'
const C_FAINT        = '#61708a'
const C_POS          = '#4fd1c5'   // teal – positive weight
const C_NEG          = '#f7768e'   // red  – negative weight

// ─── Layout constants ────────────────────────────────────────────────────────

const VB_W = 440
const VB_H = 300
const R    = 19           // node radius

const X_IN  = 70
const X_HID = 220
const X_OUT = 370
const Y_MID = 150

const HID_TOP    = 55
const HID_BOT    = 245

const CAPTION_Y  = 288

// ─── Helpers ─────────────────────────────────────────────────────────────────

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}

function edgeColor(w: number): string {
  return w >= 0 ? C_POS : C_NEG
}

function strokeW(w: number, scale: number, lo: number, hi: number): number {
  return clamp(Math.abs(w) * scale, lo, hi)
}

function fmt(v: number): string {
  return v.toFixed(2)
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface NetworkDiagramProps {
  neurons: number
  w:  number          // input→output weight  (neurons === 1)
  b:  number          // output bias           (neurons === 1)
  w1: number[]        // input→hidden weights  (length neurons, neurons >= 2)
  b1: number[]        // hidden biases
  w2: number[]        // hidden→output weights
  b2: number          // output bias            (neurons >= 2)
  activations?: number[]  // optional hidden activations (length neurons)
}

// ─── Sub-components ──────────────────────────────────────────────────────────

interface NodeProps {
  cx: number
  cy: number
  label: string
  strokeColor: string
}

function Node({ cx, cy, label, strokeColor }: NodeProps) {
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={R}
        fill={C_NODE_FILL}
        stroke={strokeColor}
        strokeWidth={2}
      />
      <text
        x={cx}
        y={cy}
        fill={C_TEXT}
        fontSize={12}
        fontWeight={700}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {label}
      </text>
    </g>
  )
}

interface EdgeProps {
  x1: number; y1: number
  x2: number; y2: number
  weight: number
  scaleWidth: number
  swLo: number
  swHi: number
  showLabel?: boolean
  labelX?: number
  labelY?: number
  labelText?: string
}

function Edge({
  x1, y1, x2, y2,
  weight, scaleWidth, swLo, swHi,
  showLabel, labelX, labelY, labelText,
}: EdgeProps) {
  const sw    = strokeW(weight, scaleWidth, swLo, swHi)
  const color = edgeColor(weight)
  return (
    <g>
      <line
        x1={x1} y1={y1}
        x2={x2} y2={y2}
        stroke={color}
        strokeWidth={sw}
        opacity={0.8}
      />
      {showLabel && labelX !== undefined && labelY !== undefined && (
        <text
          x={labelX}
          y={labelY}
          fill={C_FAINT}
          fontSize={9}
          textAnchor="middle"
          dominantBaseline="central"
        >
          {labelText ?? fmt(weight)}
        </text>
      )}
    </g>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function NetworkDiagram(props: NetworkDiagramProps): JSX.Element {
  const { neurons, w, b, w1, b1, w2, b2, activations } = props

  // ── Regime: single neuron (linear) ─────────────────────────────────────────
  if (neurons === 1) {
    const midX = (X_IN + X_OUT) / 2
    const midY = Y_MID - 12

    return (
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Edge */}
        <Edge
          x1={X_IN}  y1={Y_MID}
          x2={X_OUT} y2={Y_MID}
          weight={w}
          scaleWidth={2.2}
          swLo={1.2}
          swHi={9}
          showLabel
          labelX={midX}
          labelY={midY}
          labelText={`w=${fmt(w)}`}
        />

        {/* Nodes */}
        <Node cx={X_IN}  cy={Y_MID} label="x"  strokeColor={C_INPUT_STROKE}  />
        <Node cx={X_OUT} cy={Y_MID} label="ŷ"  strokeColor={C_OUTPUT_STROKE} />

        {/* Output bias */}
        <text
          x={X_OUT}
          y={Y_MID + R + 14}
          fill={C_FAINT}
          fontSize={10}
          textAnchor="middle"
          dominantBaseline="central"
        >
          b={fmt(b)}
        </text>

        {/* Caption */}
        <text
          x={VB_W / 2}
          y={CAPTION_Y}
          fill={C_DIM}
          fontSize={11}
          textAnchor="middle"
          dominantBaseline="central"
        >
          1 neurone → une droite
        </text>
      </svg>
    )
  }

  // ── Regime: hidden ReLU layer ───────────────────────────────────────────────

  // Vertical positions for hidden nodes (neurons >= 2 here)
  const hiddenY: number[] = Array.from({ length: neurons }, (_, i) =>
    HID_TOP + (i / (neurons - 1)) * (HID_BOT - HID_TOP)
  )

  // Activation glow: normalize to [0, 1]
  let normAct: number[] | undefined
  if (activations && activations.length >= neurons) {
    const maxAct = Math.max(...activations.slice(0, neurons).map(Math.abs), 1e-9)
    normAct = activations.slice(0, neurons).map(a => Math.abs(a) / maxAct)
  }

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* ── Edges: input → hidden ──────────────────────────────────────────── */}
      {hiddenY.map((hy, i) => {
        const wi = w1[i] ?? 0
        return (
          <Edge
            key={`e-in-h${i}`}
            x1={X_IN}  y1={Y_MID}
            x2={X_HID} y2={hy}
            weight={wi}
            scaleWidth={2.2}
            swLo={1}
            swHi={8}
            showLabel
            labelX={(X_IN + X_HID) / 2}
            labelY={(Y_MID + hy) / 2 - 6}
            labelText={`${fmt(wi)}`}
          />
        )
      })}

      {/* ── Edges: hidden → output ─────────────────────────────────────────── */}
      {hiddenY.map((hy, i) => {
        const wi = w2[i] ?? 0
        return (
          <Edge
            key={`e-h${i}-out`}
            x1={X_HID} y1={hy}
            x2={X_OUT} y2={Y_MID}
            weight={wi}
            scaleWidth={2.2}
            swLo={1}
            swHi={8}
            showLabel
            labelX={(X_HID + X_OUT) / 2}
            labelY={(hy + Y_MID) / 2 - 6}
            labelText={`${fmt(wi)}`}
          />
        )
      })}

      {/* ── Hidden nodes ──────────────────────────────────────────────────── */}
      {hiddenY.map((hy, i) => {
        const glowOpacity = normAct ? normAct[i] : 0
        return (
          <g key={`h${i}`}>
            {/* Activation glow disk */}
            {normAct !== undefined && (
              <circle
                cx={X_HID}
                cy={hy}
                r={R + 5}
                fill={C_HIDDEN_STROKE}
                opacity={glowOpacity * 0.45}
              />
            )}
            <Node cx={X_HID} cy={hy} label={`h${i + 1}`} strokeColor={C_HIDDEN_STROKE} />
            {/* Hidden bias label */}
            <text
              x={X_HID + R + 4}
              y={hy + R + 2}
              fill={C_FAINT}
              fontSize={9}
              textAnchor="start"
              dominantBaseline="hanging"
            >
              b={fmt(b1[i] ?? 0)}
            </text>
          </g>
        )
      })}

      {/* ── Input node ───────────────────────────────────────────────────── */}
      <Node cx={X_IN}  cy={Y_MID} label="x"  strokeColor={C_INPUT_STROKE}  />

      {/* ── Output node ──────────────────────────────────────────────────── */}
      <Node cx={X_OUT} cy={Y_MID} label="ŷ"  strokeColor={C_OUTPUT_STROKE} />

      {/* Output bias */}
      <text
        x={X_OUT}
        y={Y_MID + R + 14}
        fill={C_FAINT}
        fontSize={10}
        textAnchor="middle"
        dominantBaseline="central"
      >
        b2={fmt(b2)}
      </text>

      {/* Caption */}
      <text
        x={VB_W / 2}
        y={CAPTION_Y}
        fill={C_DIM}
        fontSize={11}
        textAnchor="middle"
        dominantBaseline="central"
      >
        {neurons} neurones ReLU → {neurons} morceaux linéaires combinés
      </text>
    </svg>
  )
}
