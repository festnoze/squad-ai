import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // Core React libraries
          react: ['react', 'react-dom', 'react-router-dom'],
          // Chart libraries
          charts: ['chart.js', 'react-chartjs-2', 'chartjs-chart-financial', 'chartjs-adapter-date-fns', 'recharts'],
          // Data fetching and state management
          data: ['react-query', 'zustand', 'axios'],
          // UI and utilities
          ui: ['lucide-react', 'clsx', 'tailwind-merge', 'react-hot-toast', 'react-hook-form'],
          // Table functionality
          table: ['@tanstack/react-table'],
          // Date utilities
          dates: ['date-fns'],
          // Socket connection
          socket: ['socket.io-client']
        }
      }
    },
    chunkSizeWarningLimit: 600
  },
})