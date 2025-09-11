import { NavLink } from 'react-router-dom'
import {
  BarChart3,
  TrendingUp,
  Wallet,
  Brain,
  Settings,
  Home,
  Activity
} from 'lucide-react'

interface SidebarProps {
  isOpen: boolean
}

const navigationItems = [
  { to: '/', label: 'Dashboard', icon: Home },
  { to: '/charts', label: 'Charts', icon: BarChart3 },
  { to: '/trading', label: 'Trading', icon: TrendingUp },
  { to: '/portfolio', label: 'Portfolio', icon: Wallet },
  { to: '/strategies', label: 'Strategies', icon: Brain },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar({ isOpen }: SidebarProps) {
  return (
    <aside
      className={`fixed left-0 top-16 h-[calc(100vh-64px)] bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 transition-all duration-300 z-40 ${
        isOpen ? 'w-64' : 'w-16'
      }`}
    >
      <div className="flex flex-col h-full">
        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-2">
          {navigationItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                      : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
                  }`
                }
              >
                <Icon className={`h-5 w-5 ${isOpen ? 'mr-3' : ''}`} />
                {isOpen && <span>{item.label}</span>}
              </NavLink>
            )
          })}
        </nav>

        {/* Status section */}
        {isOpen && (
          <div className="p-3 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center space-x-2">
              <Activity className="h-4 w-4 text-green-500" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-gray-900 dark:text-white">
                  System Status
                </p>
                <p className="text-xs text-green-600 dark:text-green-400">
                  All systems operational
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}