import { useLab } from '../store'
import { MODES } from '../camps'

function statusLabel(status: string): string {
  if (status === 'open') return 'Connecté'
  if (status === 'connecting') return 'Connexion…'
  return 'Déconnecté'
}

export function Toolbar() {
  const status = useLab((s) => s.status)
  const playing = useLab((s) => s.playing)
  const latestGen = useLab((s) => s.latestGen)
  const fitnessMax = useLab((s) => s.fitnessMax)
  const fitnessMean = useLab((s) => s.fitnessMean)
  const species = useLab((s) => s.species)
  const complexity = useLab((s) => s.complexity)

  const control = useLab((s) => s.control)
  const setField = useLab((s) => s.setField)
  const applyConfig = useLab((s) => s.applyConfig)
  const config = useLab((s) => s.config)
  const draft = useLab((s) => s.draft)
  const applying = useLab((s) => s.applying)

  const connected = status === 'open'
  const activeMode = { ...config, ...draft }.mode

  const setMode = (value: string) => {
    setField('mode', value)
    applyConfig()
  }

  return (
    <div className="toolbar">
      <div className="brand">
        <span className="dot" />
        NEAT Flappy Lab
      </div>

      <span className={`pill ${status}`}>
        {status === 'connecting' ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <span className="led" />}
        {statusLabel(status)}
      </span>

      {applying && (
        <span className="pill" title="Application de la configuration">
          <span className="spinner" style={{ width: 10, height: 10 }} />
          Application…
        </span>
      )}

      <div className="segmented">
        {MODES.map((m) => (
          <button
            key={m.value}
            className={activeMode === m.value ? 'active' : undefined}
            disabled={!connected}
            onClick={() => setMode(m.value)}
            title={m.title}
          >
            {m.label}
          </button>
        ))}
      </div>

      <button
        className="btn primary"
        disabled={!connected || playing}
        onClick={() => control('play')}
      >
        ▶ Play
      </button>
      <button
        className="btn"
        disabled={!connected || !playing}
        onClick={() => control('pause')}
      >
        ⏸ Pause
      </button>
      <button
        className="btn"
        disabled={!connected}
        onClick={() => control('step')}
        title="1 génération"
      >
        ⤳ Step
      </button>
      <button
        className="btn"
        disabled={!connected}
        onClick={() => control('reset')}
      >
        ↺ Reset
      </button>

      <div className="spacer" />

      <div className="stat">
        <span className="k">Génération</span>
        <span className="v">{latestGen >= 0 ? latestGen : '—'}</span>
      </div>
      <div className="stat">
        <span className="k">Fitness max</span>
        <span className="v">{fitnessMax.toFixed(1)}</span>
      </div>
      <div className="stat">
        <span className="k">Fitness moy</span>
        <span className="v">{fitnessMean.toFixed(1)}</span>
      </div>
      <div className="stat">
        <span className="k">Espèces</span>
        <span className="v">{species}</span>
      </div>
      <div className="stat">
        <span className="k">Complexité</span>
        <span className="v">{complexity.toFixed(1)}</span>
      </div>
    </div>
  )
}
