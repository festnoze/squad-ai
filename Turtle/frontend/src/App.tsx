import { Routes, Route } from 'react-router-dom'
import { Navbar } from '@/components/common/Navbar'
import { Sidebar } from '@/components/common/Sidebar'
import { Dashboard } from '@/components/dashboard/Dashboard'
import { ChartsPage } from '@/components/charts/ChartsPage'
import { TradingPage } from '@/components/trading/TradingPage'
import { PortfolioPage } from '@/components/portfolio/PortfolioPage'
import { StrategiesPage } from '@/components/strategies/StrategiesPage'
import { SettingsPage } from '@/components/settings/SettingsPage'
import { useAppStore } from '@/stores/appStore'

function App() {
  const { sidebarOpen } = useAppStore()

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <div className="flex h-[calc(100vh-64px)]">
        <Sidebar isOpen={sidebarOpen} />
        <main className={`flex-1 overflow-auto transition-all duration-300 ${
          sidebarOpen ? 'ml-64' : 'ml-16'
        }`}>
          <div className="p-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/charts" element={<ChartsPage />} />
              <Route path="/trading" element={<TradingPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/strategies" element={<StrategiesPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}

export default App