import { useEffect, useState } from 'react'
import { useLab } from './store'
import { Sidebar } from './components/Sidebar'
import { Toolbar } from './components/Toolbar'
import { StatusBar } from './components/StatusBar'
import { GameCanvas } from './components/GameCanvas'
import { NetworkGraph } from './components/NetworkGraph'
import { FitnessChart } from './components/FitnessChart'
import { Leaderboard } from './components/Leaderboard'
import { CurriculumNav, type LessonId } from './components/CurriculumNav'
import { LessonLabs } from './components/LessonLabs'

function FlappyDashboard() {
  return (
    <>
      <Toolbar />
      <StatusBar />
      <div className="panels">
        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Jeu - population</span>
            <span className="panel-title" id="game-hint" />
          </div>
          <div className="panel-body">
            <GameCanvas />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Reseau - oiseau selectionne</span>
          </div>
          <div className="panel-body">
            <NetworkGraph />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Courbes d'evolution</span>
          </div>
          <div className="panel-body">
            <FitnessChart />
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Classement</span>
          </div>
          <div className="panel-body">
            <Leaderboard />
          </div>
        </section>
      </div>
    </>
  )
}

export default function App() {
  const connect = useLab((s) => s.connect)
  const fetchSchema = useLab((s) => s.fetchSchema)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeLesson, setActiveLesson] = useState<LessonId>('linear')

  useEffect(() => {
    if (activeLesson === 'flappy') {
      fetchSchema()
      connect()
    }
  }, [activeLesson, connect, fetchSchema])

  return (
    <div
      className={`app ${activeLesson === 'flappy' ? 'flappy-active' : 'lesson-active'} ${
        sidebarOpen ? '' : 'sidebar-collapsed'
      }`}
    >
      <aside className="sidebar">
        <div className="sidebar-inner curriculum-shell">
          <CurriculumNav active={activeLesson} onChange={setActiveLesson} />
        </div>
        {activeLesson === 'flappy' && <Sidebar />}
      </aside>

      <button
        className="sidebar-toggle"
        title={sidebarOpen ? 'Masquer le panneau' : 'Afficher le panneau'}
        onClick={() => setSidebarOpen((v) => !v)}
      >
        {sidebarOpen ? '<' : '>'}
      </button>

      <div className="main">
        {activeLesson === 'flappy' ? <FlappyDashboard /> : <LessonLabs active={activeLesson} />}
      </div>
    </div>
  )
}

