import { useState } from 'react'

export interface Experiment {
  id: string
  title: string
  question: string
  options: { key: string; label: string }[]
  answerKey: string
  reveal: string
  applyLabel?: string
}

export function ExperimentCards({
  experiments,
  onApply,
}: {
  experiments: Experiment[]
  onApply: (id: string) => void
}): JSX.Element {
  const [choices, setChoices] = useState<Record<string, string | null>>({})

  function handleOptionClick(experimentId: string, optionKey: string): void {
    setChoices((prev) => ({ ...prev, [experimentId]: optionKey }))
  }

  return (
    <div className="experiments">
      {experiments.map((xp) => {
        const chosen = choices[xp.id] ?? null
        const hasChosen = chosen !== null

        return (
          <div key={xp.id} className="xp-card">
            <div className="xp-title">{xp.title}</div>
            <div className="xp-question">{xp.question}</div>

            <div className="xp-options">
              {xp.options.map((opt) => {
                let optClassName = 'xp-option'
                if (hasChosen) {
                  if (opt.key === chosen) {
                    optClassName += ' chosen'
                  }
                  if (opt.key === xp.answerKey) {
                    optClassName += ' correct'
                  }
                  if (opt.key === chosen && chosen !== xp.answerKey) {
                    optClassName += ' wrong'
                  }
                }

                return (
                  <button
                    key={opt.key}
                    className={optClassName}
                    onClick={() => handleOptionClick(xp.id, opt.key)}
                  >
                    {opt.label}
                  </button>
                )
              })}
            </div>

            {hasChosen && (
              <>
                <p className="xp-reveal">{xp.reveal}</p>
                <button
                  className="xp-apply"
                  onClick={() => onApply(xp.id)}
                >
                  {xp.applyLabel ?? 'Appliquer dans la démo'}
                </button>
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}
