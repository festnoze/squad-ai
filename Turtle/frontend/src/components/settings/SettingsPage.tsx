import { useState, useEffect } from 'react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAppStore } from '@/stores/appStore'

interface SettingsData {
  apiUrl: string
  defaultPortfolio: string
  riskPerTrade: number
  maxOpenTrades: number
  autoTradingEnabled: boolean
  notifications: {
    email: boolean
    browser: boolean
    tradeExecutions: boolean
    significantPnL: boolean
  }
  display: {
    darkMode: boolean
    compactView: boolean
    showAdvancedMetrics: boolean
  }
}

export function SettingsPage() {
  const { darkMode } = useAppStore()
  const [settings, setSettings] = useState<SettingsData>({
    apiUrl: 'http://localhost:8000',
    defaultPortfolio: '',
    riskPerTrade: 2,
    maxOpenTrades: 5,
    autoTradingEnabled: false,
    notifications: {
      email: true,
      browser: true,
      tradeExecutions: true,
      significantPnL: true
    },
    display: {
      darkMode: darkMode,
      compactView: false,
      showAdvancedMetrics: false
    }
  })

  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    // Load settings from localStorage or API
    const savedSettings = localStorage.getItem('turtle-trading-settings')
    if (savedSettings) {
      try {
        const parsed = JSON.parse(savedSettings)
        setSettings({ ...settings, ...parsed })
      } catch (error) {
        console.error('Error loading settings:', error)
      }
    }
  }, [])

  const handleSave = async () => {
    setIsSaving(true)
    try {
      // Save to localStorage (in a real app, this would be an API call)
      localStorage.setItem('turtle-trading-settings', JSON.stringify(settings))
      
      // Update app store if needed
      if (settings.display.darkMode !== darkMode) {
        useAppStore.getState().toggleDarkMode()
      }
      
      // Show success message
      console.log('Settings saved successfully')
    } catch (error) {
      console.error('Error saving settings:', error)
    } finally {
      setIsSaving(false)
    }
  }

  const handleReset = () => {
    setSettings({
      apiUrl: 'http://localhost:8000',
      defaultPortfolio: '',
      riskPerTrade: 2,
      maxOpenTrades: 5,
      autoTradingEnabled: false,
      notifications: {
        email: true,
        browser: true,
        tradeExecutions: true,
        significantPnL: true
      },
      display: {
        darkMode: false,
        compactView: false,
        showAdvancedMetrics: false
      }
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
        <div className="space-x-2">
          <Button variant="outline" onClick={handleReset}>
            Reset to Defaults
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save Settings'}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">API Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">API Base URL</label>
              <Input
                value={settings.apiUrl}
                onChange={(e) => setSettings(prev => ({ ...prev, apiUrl: e.target.value }))}
                placeholder="http://localhost:8000"
              />
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Trading Settings</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Default Portfolio</label>
              <Input
                value={settings.defaultPortfolio}
                onChange={(e) => setSettings(prev => ({ ...prev, defaultPortfolio: e.target.value }))}
                placeholder="Enter portfolio ID"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Risk Per Trade (%)</label>
              <Input
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                value={settings.riskPerTrade}
                onChange={(e) => setSettings(prev => ({ ...prev, riskPerTrade: Number(e.target.value) }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Max Open Trades</label>
              <Input
                type="number"
                min="1"
                max="20"
                value={settings.maxOpenTrades}
                onChange={(e) => setSettings(prev => ({ ...prev, maxOpenTrades: Number(e.target.value) }))}
              />
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="autoTrading"
                checked={settings.autoTradingEnabled}
                onChange={(e) => setSettings(prev => ({ ...prev, autoTradingEnabled: e.target.checked }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="autoTrading" className="text-sm font-medium">
                Enable Auto Trading
              </label>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Notifications</h3>
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="emailNotifications"
                checked={settings.notifications.email}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, email: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="emailNotifications" className="text-sm font-medium">
                Email Notifications
              </label>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="browserNotifications"
                checked={settings.notifications.browser}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, browser: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="browserNotifications" className="text-sm font-medium">
                Browser Notifications
              </label>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="tradeExecutions"
                checked={settings.notifications.tradeExecutions}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, tradeExecutions: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="tradeExecutions" className="text-sm font-medium">
                Trade Executions
              </label>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="significantPnL"
                checked={settings.notifications.significantPnL}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  notifications: { ...prev.notifications, significantPnL: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="significantPnL" className="text-sm font-medium">
                Significant P&L Changes
              </label>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Display Settings</h3>
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="darkMode"
                checked={settings.display.darkMode}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  display: { ...prev.display, darkMode: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="darkMode" className="text-sm font-medium">
                Dark Mode
              </label>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="compactView"
                checked={settings.display.compactView}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  display: { ...prev.display, compactView: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="compactView" className="text-sm font-medium">
                Compact View
              </label>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="showAdvancedMetrics"
                checked={settings.display.showAdvancedMetrics}
                onChange={(e) => setSettings(prev => ({
                  ...prev,
                  display: { ...prev.display, showAdvancedMetrics: e.target.checked }
                }))}
                className="rounded border-gray-300"
              />
              <label htmlFor="showAdvancedMetrics" className="text-sm font-medium">
                Show Advanced Metrics
              </label>
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">System Information</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-gray-600">Frontend Version</div>
            <div className="font-medium">1.0.0</div>
          </div>
          <div>
            <div className="text-gray-600">API Status</div>
            <div className="font-medium text-green-600">Connected</div>
          </div>
          <div>
            <div className="text-gray-600">Last Updated</div>
            <div className="font-medium">{new Date().toLocaleDateString()}</div>
          </div>
          <div>
            <div className="text-gray-600">Environment</div>
            <div className="font-medium">Development</div>
          </div>
        </div>
      </Card>
    </div>
  )
}