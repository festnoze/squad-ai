import type { CSSProperties } from 'react'
import { useLab } from '../store'
import { CAMP_COLORS, CAMP_LABELS } from '../camps'

const wrapStyle: CSSProperties = {
  padding: '8px 10px',
  overflowY: 'auto',
}

const rowStyle: CSSProperties = {
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  height: 34,
  padding: '0 10px',
  borderRadius: 'var(--radius-sm)',
  border: '1px solid transparent',
  borderLeft: '2px solid transparent',
  cursor: 'pointer',
  userSelect: 'none',
  overflow: 'hidden',
  transition: 'background 0.12s ease, border-color 0.12s ease',
}

const rankStyle: CSSProperties = {
  width: 30,
  flex: '0 0 auto',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-faint)',
  fontVariantNumeric: 'tabular-nums',
}

const nameStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  color: 'var(--text)',
}

const fitnessStyle: CSSProperties = {
  flex: '0 0 auto',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  fontVariantNumeric: 'tabular-nums',
  fontWeight: 600,
  color: 'var(--accent)',
}

const badgeStyle: CSSProperties = {
  flex: '0 0 auto',
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: '0.06em',
  padding: '1px 7px',
  borderRadius: 999,
  border: '1px solid',
  lineHeight: '14px',
}

export function Leaderboard() {
  const leaderboard = useLab((s) => s.leaderboard)
  const selectedBirdId = useLab((s) => s.selectedBirdId)
  const select = useLab((s) => s.select)

  if (leaderboard.length === 0) {
    return (
      <div className="empty-hint">
        Le classement s'affichera après la première génération.
      </div>
    )
  }

  const maxFitness = leaderboard[0]?.fitness || 0

  return (
    <div className="fill" style={wrapStyle}>
      {leaderboard.map((entry, i) => {
        const selected = entry.birdId === selectedBirdId
        const pct =
          maxFitness > 0 ? Math.max(0, Math.min(1, entry.fitness / maxFitness)) : 0

        return (
          <div
            key={entry.birdId}
            role="button"
            tabIndex={0}
            onClick={() => select(entry.birdId)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                select(entry.birdId)
              }
            }}
            style={{
              ...rowStyle,
              marginBottom: 4,
              background: selected ? 'var(--bg-elev-3)' : 'transparent',
              borderLeftColor: selected ? 'var(--accent)' : 'transparent',
            }}
            onMouseEnter={(e) => {
              if (!selected) e.currentTarget.style.background = 'var(--bg-elev-2)'
            }}
            onMouseLeave={(e) => {
              if (!selected) e.currentTarget.style.background = 'transparent'
            }}
          >
            <span style={rankStyle}>#{i + 1}</span>
            <span style={nameStyle}>Oiseau {entry.birdId}</span>
            {entry.camp && (
              <span
                style={{
                  ...badgeStyle,
                  color: CAMP_COLORS[entry.camp],
                  borderColor: CAMP_COLORS[entry.camp],
                }}
                title={
                  entry.camp === 'neat'
                    ? 'Entraîné par évolution (NEAT)'
                    : entry.camp === 'gd'
                      ? 'Entraîné par descente de gradient'
                      : 'Hybride évolution + gradient'
                }
              >
                {CAMP_LABELS[entry.camp]}
              </span>
            )}
            <span style={fitnessStyle}>{entry.fitness.toFixed(1)}</span>

            {/* thin fitness bar pinned to the bottom of the row */}
            <span
              style={{
                position: 'absolute',
                left: 0,
                bottom: 0,
                height: 2,
                width: `${pct * 100}%`,
                background: 'var(--accent)',
                opacity: selected ? 0.9 : 0.45,
                borderRadius: 1,
                pointerEvents: 'none',
              }}
            />
          </div>
        )
      })}
    </div>
  )
}
