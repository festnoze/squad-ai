import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useLab } from '../store'
import { CAMP_COLORS } from '../camps'

// Recharts renders to SVG, where CSS custom properties (var(--x)) are unreliable
// as attribute values. We mirror the design-system tokens as concrete hex strings.
const COLOR = {
  fitnessMax: '#4fd1c5', // var(--accent) — teal
  fitnessMean: '#7c9cff', // var(--accent-2) — indigo
  species: '#f6c177', // var(--warn) — amber
  complexity: '#9ece6a', // var(--ok) — green
  tick: '#9fb0c8', // var(--text-dim)
  grid: '#25304a', // var(--panel-border)
}

const TOOLTIP_STYLE = {
  background: '#131a26',
  border: '1px solid #25304a',
  borderRadius: 8,
  color: '#e7edf7',
} as const

const AXIS_TICK = { fill: COLOR.tick, fontSize: 11 }
const LEGEND_STYLE = { fontSize: 11, color: COLOR.tick }

const titleStyle: React.CSSProperties = {
  fontSize: 12,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--text-dim)',
  padding: '6px 4px 2px',
  flex: '0 0 auto',
}

const sectionStyle: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
}

export function FitnessChart() {
  const generations = useLab((s) => s.generations)

  if (generations.length === 0) {
    return (
      <div className="empty-hint">
        Les courbes apparaîtront après la première génération.
      </div>
    )
  }

  // Confrontation data present → compare the two camps explicitly instead of
  // showing a single merged curve.
  const duel = generations.some((g) => g.neatMax != null && g.gdMax != null)

  return (
    <div
      className="fill"
      style={{ display: 'flex', flexDirection: 'column' }}
    >
      {/* ---- Fitness ---- */}
      <div style={sectionStyle}>
        <div style={titleStyle}>{duel ? 'Fitness — NEAT vs GD' : 'Fitness'}</div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={generations}
              margin={{ top: 6, right: 16, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke={COLOR.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="gen"
                tick={AXIS_TICK}
                stroke={COLOR.grid}
                tickLine={{ stroke: COLOR.grid }}
              />
              <YAxis
                tick={AXIS_TICK}
                stroke={COLOR.grid}
                tickLine={{ stroke: COLOR.grid }}
                width={44}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: COLOR.tick }} />
              <Legend wrapperStyle={LEGEND_STYLE} />
              {duel ? (
                <>
                  <Line
                    type="monotone"
                    dataKey="neatMax"
                    name="NEAT max"
                    stroke={CAMP_COLORS.neat}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="gdMax"
                    name="GD max"
                    stroke={CAMP_COLORS.gd}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="neatMean"
                    name="NEAT moy"
                    stroke={CAMP_COLORS.neat}
                    strokeDasharray="4 4"
                    dot={false}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="gdMean"
                    name="GD moy"
                    stroke={CAMP_COLORS.gd}
                    strokeDasharray="4 4"
                    dot={false}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                  />
                </>
              ) : (
                <>
                  <Line
                    type="monotone"
                    dataKey="fitnessMax"
                    name="Max"
                    stroke={COLOR.fitnessMax}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="fitnessMean"
                    name="Moyenne"
                    stroke={COLOR.fitnessMean}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                </>
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ---- Structure ---- */}
      <div style={sectionStyle}>
        <div style={titleStyle}>Structure</div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={generations}
              margin={{ top: 6, right: 16, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke={COLOR.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="gen"
                tick={AXIS_TICK}
                stroke={COLOR.grid}
                tickLine={{ stroke: COLOR.grid }}
              />
              <YAxis
                yAxisId="species"
                tick={AXIS_TICK}
                stroke={COLOR.species}
                tickLine={{ stroke: COLOR.grid }}
                width={44}
              />
              <YAxis
                yAxisId="complexity"
                orientation="right"
                tick={AXIS_TICK}
                stroke={COLOR.complexity}
                tickLine={{ stroke: COLOR.grid }}
                width={44}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: COLOR.tick }} />
              <Legend wrapperStyle={LEGEND_STYLE} />
              <Line
                yAxisId="species"
                type="monotone"
                dataKey="species"
                name="Espèces"
                stroke={COLOR.species}
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
              <Line
                yAxisId="complexity"
                type="monotone"
                dataKey="complexity"
                name="Complexité"
                stroke={COLOR.complexity}
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
