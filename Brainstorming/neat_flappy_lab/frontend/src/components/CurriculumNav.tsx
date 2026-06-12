export type LessonId = 'linear' | 'quadratic' | 'neat' | 'flappy'

interface LessonMeta {
  id: LessonId
  index: string
  title: string
  subtitle: string
}

export const LESSONS: LessonMeta[] = [
  {
    id: 'linear',
    index: '01',
    title: 'Regression lineaire',
    subtitle: 'Une droite, une loss, deux parametres.',
  },
  {
    id: 'quadratic',
    index: '02',
    title: 'Reseau quadratique',
    subtitle: 'Des neurones qui construisent une courbe.',
  },
  {
    id: 'neat',
    index: '03',
    title: 'NEAT par XOR',
    subtitle: 'Population, especes et innovations.',
  },
  {
    id: 'flappy',
    index: '04',
    title: 'Flappy lab',
    subtitle: 'NEAT + gradient descent en simulation.',
  },
]

interface Props {
  active: LessonId
  onChange: (id: LessonId) => void
}

export function CurriculumNav({ active, onChange }: Props) {
  return (
    <div className="curriculum-nav">
      <div className="curriculum-brand">
        <span className="dot" />
        <div>
          <h1>NEAT Lab</h1>
          <p>Apprendre par traces visuelles</p>
        </div>
      </div>

      <div className="lesson-list" aria-label="Parcours didactique">
        {LESSONS.map((lesson) => (
          <button
            key={lesson.id}
            className={`lesson-tab ${active === lesson.id ? 'active' : ''}`}
            onClick={() => onChange(lesson.id)}
          >
            <span className="lesson-index">{lesson.index}</span>
            <span>
              <b>{lesson.title}</b>
              <small>{lesson.subtitle}</small>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

