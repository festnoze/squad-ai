import { Menu, X, TrendingUp, Settings, Moon, Sun } from 'lucide-react'
import { useAppStore } from '@/stores/appStore'

export function Navbar() {
  const { sidebarOpen, toggleSidebar, darkMode, toggleDarkMode } = useAppStore()

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 h-16 flex items-center justify-between px-4 shadow-sm">
      {/* Left section */}
      <div className="flex items-center space-x-4">
        <button
          onClick={toggleSidebar}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          {sidebarOpen ? (
            <X className="h-5 w-5 text-gray-600 dark:text-gray-300" />
          ) : (
            <Menu className="h-5 w-5 text-gray-600 dark:text-gray-300" />
          )}
        </button>
        
        <div className="flex items-center space-x-2">
          <TrendingUp className="h-8 w-8 text-primary-600" />
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">
              Turtle Trading Bot
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Advanced Trading Strategy Platform
            </p>
          </div>
        </div>
      </div>

      {/* Right section */}
      <div className="flex items-center space-x-3">
        {/* Theme toggle */}
        <button
          onClick={toggleDarkMode}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {darkMode ? (
            <Sun className="h-5 w-5 text-yellow-500" />
          ) : (
            <Moon className="h-5 w-5 text-gray-600" />
          )}
        </button>

        {/* Settings */}
        <button className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
          <Settings className="h-5 w-5 text-gray-600 dark:text-gray-300" />
        </button>

        {/* Status indicator */}
        <div className="flex items-center space-x-2">
          <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-sm text-gray-600 dark:text-gray-300">Connected</span>
        </div>
      </div>
    </nav>
  )
}