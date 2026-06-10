import { create } from 'zustand'
import type {
  Camp,
  CampStat,
  ConfigSchema,
  ConnStatus,
  ControlAction,
  FrameMsg,
  Genome,
  GenerationRow,
  LeaderboardEntry,
  ServerMsg,
} from './types'

const API_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000'
const WS_URL = (import.meta.env.VITE_WS_URL as string) || 'ws://localhost:8000/ws'

const MAX_HISTORY = 600

// Mirror backend STRUCTURAL_FIELDS: changing these starts a fresh run (the
// server rebuilds and emits a reset), so the UI stops playing too.
const STRUCTURAL_KEYS = new Set([
  'pop_size',
  'active_sensors',
  'initial_hidden',
  'max_nodes',
  'max_connections',
  'seed',
  'gd_ratio',
])

// The live socket lives outside React state (it isn't serializable / renderable).
let socket: WebSocket | null = null

interface LabState {
  status: ConnStatus
  schema: ConfigSchema | null
  /** Server-confirmed config (echoed back on apply). */
  config: Record<string, any>
  /** Local edits not yet applied; merged over `config` for display. */
  draft: Record<string, any>
  dirty: boolean
  /** True while an applied config patch is in flight (waiting for the echo). */
  applying: boolean
  playing: boolean

  frame: FrameMsg | null
  generations: GenerationRow[]
  bestGenome: Genome | null
  latestGen: number
  fitnessMax: number
  fitnessMean: number
  species: number
  complexity: number

  selectedBirdId: number | null
  selectedGenome: Genome | null
  leaderboard: LeaderboardEntry[]

  /** Per-camp aggregates of the latest generation (confrontation mode). */
  camps: Record<string, CampStat> | null
  /** Camp of the latest generation's best bird. */
  winnerCamp: Camp | null
  /** Cumulative generations won by each camp since the last reset. */
  campWins: { neat: number; gd: number }

  lastError: string | null

  // actions
  connect: () => void
  fetchSchema: () => Promise<void>
  setField: (key: string, value: any) => void
  resetDraft: () => void
  applyConfig: () => void
  control: (action: ControlAction) => void
  select: (birdId: number) => void
  /** Config value with local draft overrides applied (for controlled inputs). */
  effectiveConfig: () => Record<string, any>
}

function send(message: object) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message))
  }
}

export const useLab = create<LabState>((set, get) => ({
  status: 'idle',
  schema: null,
  config: {},
  draft: {},
  dirty: false,
  applying: false,
  playing: false,

  frame: null,
  generations: [],
  bestGenome: null,
  latestGen: -1,
  fitnessMax: 0,
  fitnessMean: 0,
  species: 0,
  complexity: 0,

  selectedBirdId: null,
  selectedGenome: null,
  leaderboard: [],

  camps: null,
  winnerCamp: null,
  campWins: { neat: 0, gd: 0 },

  lastError: null,

  connect: () => {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return
    }
    set({ status: 'connecting' })
    const ws = new WebSocket(WS_URL)
    socket = ws

    ws.onopen = () => set({ status: 'open' })
    ws.onclose = () => set({ status: 'closed', playing: false })
    ws.onerror = () => set({ status: 'closed' })

    ws.onmessage = (ev) => {
      let msg: ServerMsg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      switch (msg.type) {
        case 'frame':
          set({ frame: msg })
          break
        case 'generation': {
          const row: GenerationRow = {
            gen: msg.gen,
            fitnessMax: msg.fitnessMax,
            fitnessMean: msg.fitnessMean,
            species: msg.species,
            complexity: msg.complexity,
          }
          const camps = msg.camps ?? null
          const isDuel = !!(camps && camps.neat && camps.gd)
          if (isDuel) {
            row.neatMax = camps!.neat.fitnessMax
            row.neatMean = camps!.neat.fitnessMean
            row.gdMax = camps!.gd.fitnessMax
            row.gdMean = camps!.gd.fitnessMean
          }
          const wins = { ...get().campWins }
          if (isDuel && (msg.winnerCamp === 'neat' || msg.winnerCamp === 'gd')) {
            wins[msg.winnerCamp] += 1
          }
          const history = [...get().generations, row].slice(-MAX_HISTORY)
          set({
            generations: history,
            bestGenome: msg.bestGenome,
            leaderboard: msg.leaderboard,
            latestGen: msg.gen,
            fitnessMax: msg.fitnessMax,
            fitnessMean: msg.fitnessMean,
            species: msg.species,
            complexity: msg.complexity,
            camps,
            winnerCamp: msg.winnerCamp ?? null,
            campWins: wins,
          })
          break
        }
        case 'genome':
          // Only adopt if it still matches the user's current selection.
          if (get().selectedBirdId === msg.birdId) {
            set({ selectedGenome: msg.genome })
          }
          break
        case 'config':
          set({
            config: { ...(msg.config as Record<string, any>) },
            draft: {},
            dirty: false,
            applying: false,
          })
          break
        case 'reset':
          set({
            frame: null,
            generations: [],
            bestGenome: null,
            selectedGenome: null,
            selectedBirdId: null,
            leaderboard: [],
            latestGen: -1,
            playing: false,
            applying: false,
            camps: null,
            winnerCamp: null,
            campWins: { neat: 0, gd: 0 },
          })
          break
        case 'error':
          set({ lastError: msg.message, applying: false })
          break
      }
    }
  },

  fetchSchema: async () => {
    try {
      const res = await fetch(`${API_URL}/config/schema`)
      const schema = (await res.json()) as ConfigSchema
      set({ schema })
    } catch (e) {
      set({ lastError: `failed to load config schema: ${String(e)}` })
    }
  },

  setField: (key, value) =>
    set((s) => ({ draft: { ...s.draft, [key]: value }, dirty: true })),

  resetDraft: () => set({ draft: {}, dirty: false }),

  applyConfig: () => {
    const { draft, status } = get()
    const keys = Object.keys(draft)
    if (keys.length === 0) return
    if (status !== 'open') return
    // Applying params always stops the current run: a STRUCTURAL change resets
    // it (server rebuilds + clears), a SOFT change just pauses it so the new
    // params take effect cleanly when the user hits play again.
    const structural = keys.some((k) => STRUCTURAL_KEYS.has(k))
    set({ applying: true, playing: false })
    send({ type: 'config', patch: draft })
    if (!structural) {
      send({ type: 'control', action: 'pause' })
    }
    // The server echoes a `config` message which clears draft/dirty/applying.
  },

  control: (action) => {
    send({ type: 'control', action })
    if (action === 'play') set({ playing: true })
    if (action === 'pause' || action === 'reset') set({ playing: false })
  },

  select: (birdId) => {
    set({ selectedBirdId: birdId, selectedGenome: null })
    send({ type: 'select', birdId })
  },

  effectiveConfig: () => {
    const { config, draft } = get()
    return { ...config, ...draft }
  },
}))
