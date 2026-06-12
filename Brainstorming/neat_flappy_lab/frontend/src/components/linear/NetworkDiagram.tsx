export interface NetworkDiagramProps {
  neurons: number
  w: number // input -> neuron weight (neurons === 1)
  b: number // neuron bias (neurons === 1)
  w1: number[] // input -> neuron i weights (neurons >= 2)
  b1: number[] // neuron i biases
  w2: number[] // neuron i -> output weights
  b2: number // output bias c (neurons >= 2)
  activations?: number[]
}

const C = {
  fill: '#1a2333',
  input: '#7c9cff',
  output: '#4fd1c5',
  neuron: '#f6c177',
  pos: '#4fd1c5',
  neg: '#f7768e',
  text: '#e7edf7',
  dim: '#9fb0c8',
  faint: '#61708a',
} as const

function edgeWidth(weight: number): number {
  return Math.max(1.2, Math.min(8, Math.abs(weight) * 2.2))
}

// A stylised biological neuron: dendrites (left) -> soma (with a glowing
// nucleus driven by its activation) -> axon + terminals (right).
function NeuronGlyph({ cx, cy, act, label, bias }: { cx: number; cy: number; act: number; label: string; bias: number }) {
  const glow = Math.max(0, Math.min(1, act))
  const dendrites: [number, number][] = [
    [-40, -14],
    [-42, -4],
    [-42, 6],
    [-38, 16],
  ]
  return (
    <g>
      {dendrites.map(([dx, dy], k) => (
        <line key={k} x1={cx - 18} y1={cy} x2={cx + dx} y2={cy + dy} stroke={C.neuron} strokeWidth={1.2} strokeOpacity={0.65} />
      ))}
      <line x1={cx + 18} y1={cy} x2={cx + 44} y2={cy} stroke={C.neuron} strokeWidth={1.6} strokeOpacity={0.8} />
      <line x1={cx + 44} y1={cy} x2={cx + 50} y2={cy - 7} stroke={C.neuron} strokeWidth={1.2} strokeOpacity={0.65} />
      <line x1={cx + 44} y1={cy} x2={cx + 50} y2={cy + 7} stroke={C.neuron} strokeWidth={1.2} strokeOpacity={0.65} />
      <ellipse cx={cx} cy={cy} rx={20} ry={16} fill={C.fill} stroke={C.neuron} strokeWidth={2} />
      <circle cx={cx} cy={cy} r={7} fill={C.neuron} opacity={0.15 + glow * 0.8} />
      <text x={cx} y={cy - 24} fill={C.faint} fontSize={9} textAnchor="middle">
        b={bias.toFixed(2)}
      </text>
      <text x={cx} y={cy + 34} fill={C.dim} fontSize={11} fontWeight={700} textAnchor="middle">
        {label}
      </text>
    </g>
  )
}

export function NetworkDiagram({ neurons, w, b, w1, b1, w2, b2, activations }: NetworkDiagramProps): JSX.Element {
  const isLine = neurons === 1
  const units = isLine
    ? [{ win: w, bias: b, wout: 1, act: 1 }]
    : Array.from({ length: neurons }, (_, i) => ({
        win: w1[i] ?? 0,
        bias: b1[i] ?? 0,
        wout: w2[i] ?? 0,
        act: activations?.[i] ?? 0,
      }))
  const maxAct = Math.max(1e-6, ...units.map((u) => Math.abs(u.act)))

  const inX = 46
  const outX = 414
  const nX = 230
  const cy = (i: number) => (isLine ? 160 : 70 + (180 * i) / (neurons - 1))

  return (
    <svg width="100%" height="100%" viewBox="0 0 460 320" preserveAspectRatio="xMidYMid meet">
      {/* weighted connections under the nodes */}
      {units.map((u, i) => {
        const y = cy(i)
        return (
          <g key={`e-${i}`}>
            <line x1={inX + 23} y1={160} x2={nX - 40} y2={y} stroke={u.win >= 0 ? C.pos : C.neg} strokeWidth={edgeWidth(u.win)} strokeOpacity={0.8} />
            <text x={(inX + 23 + nX - 40) / 2} y={(160 + y) / 2 - 5} fill={C.faint} fontSize={9} textAnchor="middle">
              {u.win.toFixed(2)}
            </text>
            <line x1={nX + 50} y1={y} x2={outX - 23} y2={160} stroke={u.wout >= 0 ? C.pos : C.neg} strokeWidth={edgeWidth(u.wout)} strokeOpacity={0.8} />
            {!isLine && (
              <text x={(nX + 50 + outX - 23) / 2} y={(y + 160) / 2 - 5} fill={C.faint} fontSize={9} textAnchor="middle">
                {u.wout.toFixed(2)}
              </text>
            )}
          </g>
        )
      })}

      {units.map((u, i) => (
        <NeuronGlyph key={`n-${i}`} cx={nX} cy={cy(i)} act={u.act / maxAct} label={`neurone ${i + 1}`} bias={u.bias} />
      ))}

      {/* input value x in a square */}
      <rect x={inX - 23} y={137} width={46} height={46} rx={8} fill={C.fill} stroke={C.input} strokeWidth={2} />
      <text x={inX} y={166} fill={C.text} fontSize={16} fontWeight={700} textAnchor="middle">
        x
      </text>

      {/* output value (prediction) in a square */}
      <rect x={outX - 23} y={137} width={46} height={46} rx={8} fill={C.fill} stroke={C.output} strokeWidth={2} />
      <text x={outX} y={166} fill={C.text} fontSize={15} fontWeight={700} textAnchor="middle">
        {'ŷ'}
      </text>
      {!isLine && (
        <text x={outX} y={202} fill={C.faint} fontSize={9} textAnchor="middle">
          + c={b2.toFixed(2)}
        </text>
      )}

      <text x={230} y={306} fill={C.dim} fontSize={11} textAnchor="middle">
        {isLine ? 'ŷ = w·x + b  (une droite)' : 'ŷ = Σ vᵢ·neuroneᵢ + c  (une courbe)'}
      </text>
    </svg>
  )
}
