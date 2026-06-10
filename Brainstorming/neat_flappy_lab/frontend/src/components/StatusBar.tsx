import { useLab } from '../store'
import { CAMP_COLORS, CAMP_LABELS, modeInfo } from '../camps'
import type { CampStat } from '../types'

/**
 * Thin strip under the toolbar that makes the current regime explicit:
 * always shows what the active mode does, and in confrontation mode becomes
 * a live NEAT-vs-GD scoreboard (best fitness, mean, generations won, leader).
 */
export function StatusBar() {
  const config = useLab((s) => s.config)
  const draft = useLab((s) => s.draft)
  const camps = useLab((s) => s.camps)
  const winnerCamp = useLab((s) => s.winnerCamp)
  const campWins = useLab((s) => s.campWins)

  const effective = { ...config, ...draft }
  const mode = String(effective.mode ?? '')
  const info = modeInfo(mode)
  if (!info) return null

  const isDuel = mode === 'confrontation'
  const neat = camps?.neat as CampStat | undefined
  const gd = camps?.gd as CampStat | undefined
  const gdRatio = typeof effective.gd_ratio === 'number' ? effective.gd_ratio : 0.5

  return (
    <div className="statusbar">
      <span className="statusbar-mode">{info.label}</span>
      <span className="statusbar-desc">{info.title}</span>

      {isDuel && (
        <div className="duel">
          <CampSide camp="neat" stat={neat} share={1 - gdRatio} wins={campWins.neat} leading={winnerCamp === 'neat'} />
          <span className="duel-vs">VS</span>
          <CampSide camp="gd" stat={gd} share={gdRatio} wins={campWins.gd} leading={winnerCamp === 'gd'} />
        </div>
      )}
    </div>
  )
}

function CampSide({
  camp,
  stat,
  share,
  wins,
  leading,
}: {
  camp: 'neat' | 'gd'
  stat: CampStat | undefined
  share: number
  wins: number
  leading: boolean
}) {
  const color = CAMP_COLORS[camp]
  return (
    <span
      className={`duel-side${leading ? ' leading' : ''}`}
      style={{ borderColor: leading ? color : 'transparent' }}
      title={
        camp === 'neat'
          ? 'Camp NEAT : évolution pure (sélection, croisement, mutation).'
          : 'Camp GD : topologie figée, apprentissage par descente de gradient uniquement.'
      }
    >
      <i className="duel-dot" style={{ background: color }} />
      <b style={{ color }}>{CAMP_LABELS[camp]}</b>
      <span className="duel-meta">{Math.round(share * 100)}%</span>
      {stat ? (
        <>
          <span className="duel-stat">
            max <b>{stat.fitnessMax.toFixed(1)}</b>
          </span>
          <span className="duel-stat">
            moy <b>{stat.fitnessMean.toFixed(1)}</b>
          </span>
        </>
      ) : (
        <span className="duel-meta">en attente…</span>
      )}
      <span className="duel-stat" title="Générations remportées (meilleur oiseau)">
        🏆 <b>{wins}</b>
      </span>
      {leading && <span className="duel-crown" title="Camp du champion actuel">★ leader</span>}
    </span>
  )
}
