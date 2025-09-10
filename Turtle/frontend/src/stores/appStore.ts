import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AppState, ChartState, TradingState } from '@/types'

interface AppStore extends AppState {
  // Actions
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleDarkMode: () => void
  setSelectedPortfolio: (portfolioId: string | null) => void
  setActiveStrategy: (strategyName: string | null) => void
}

interface ChartStore extends ChartState {
  // Actions
  setSelectedSymbol: (symbol: string | null) => void
  setSelectedInterval: (interval: string) => void
  setSelectedChartFile: (filename: string | null) => void
}

interface TradingStore extends TradingState {
  // Actions
  setAutoTradingEnabled: (enabled: boolean) => void
  setSelectedStrategy: (strategy: string | null) => void
  setRiskPerTrade: (risk: number) => void
}

// Main app store
export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      // Initial state
      sidebarOpen: true,
      darkMode: false,
      selectedPortfolio: null,
      activeStrategy: null,

      // Actions
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      toggleDarkMode: () => set((state) => ({ darkMode: !state.darkMode })),
      setSelectedPortfolio: (portfolioId) => set({ selectedPortfolio: portfolioId }),
      setActiveStrategy: (strategyName) => set({ activeStrategy: strategyName }),
    }),
    {
      name: 'turtle-app-store',
      partialize: (state) => ({
        darkMode: state.darkMode,
        selectedPortfolio: state.selectedPortfolio,
        activeStrategy: state.activeStrategy,
      }),
    }
  )
)

// Chart store
export const useChartStore = create<ChartStore>()(
  persist(
    (set) => ({
      // Initial state
      selectedSymbol: null,
      selectedInterval: '1d',
      selectedChartFile: null,

      // Actions
      setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),
      setSelectedInterval: (interval) => set({ selectedInterval: interval }),
      setSelectedChartFile: (filename) => set({ selectedChartFile: filename }),
    }),
    {
      name: 'turtle-chart-store',
    }
  )
)

// Trading store
export const useTradingStore = create<TradingStore>()(
  persist(
    (set) => ({
      // Initial state
      autoTradingEnabled: false,
      selectedStrategy: null,
      riskPerTrade: 0.02,

      // Actions
      setAutoTradingEnabled: (enabled) => set({ autoTradingEnabled: enabled }),
      setSelectedStrategy: (strategy) => set({ selectedStrategy: strategy }),
      setRiskPerTrade: (risk) => set({ riskPerTrade: risk }),
    }),
    {
      name: 'turtle-trading-store',
    }
  )
)