import { useEffect, useState } from 'react'
import { useLab } from './store'
import { Sidebar } from './components/Sidebar'
import { Toolbar } from './components/Toolbar'
import { StatusBar } from './components/StatusBar'
import { GameCanvas } from './components/GameCanvas'
import { NetworkGraph } from './components/NetworkGraph'
import { FitnessChart } from './components/FitnessChart'
import { Leaderboard } from './components/Leaderboard'

export default function App() {
  const connect = useLab((s) => s.connect)
  const fetchSchema = useLab((s) => s.fetchSchema)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  useEffect(() => {
    fetchSchema()
    connect()
  }, [connect, fetchSchema])

  return (
    <div className={`app ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
      <aside className="sidebar">
        <Sidebar />
      </aside>

      <button
        className="sidebar-toggle"
        title={sidebarOpen ? 'Masquer le panneau' : 'Afficher le panneau'}
        onClick={() => setSidebarOpen((v) => !v)}
      >
        {sidebarOpen ? '‹' : '›'}
      </button>

      <div className="main">
        <Toolbar />
        <StatusBar />
        <div className="panels">
          <section className="panel">
            <div className="panel-header">
              <span className="panel-title">Jeu — population</span>
              <span className="panel-title" id="game-hint" />
            </div>
            <div className="panel-body">
              <GameCanvas />
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <span className="panel-title">Réseau — oiseau sélectionné</span>
            </div>
            <div className="panel-body">
              <NetworkGraph />
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <span className="panel-title">Courbes d'évolution</span>
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
      </div>
    </div>
  )
}
