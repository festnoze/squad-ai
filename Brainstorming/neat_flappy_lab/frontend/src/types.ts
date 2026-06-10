// Shared types — mirror the backend WebSocket protocol (see backend nfl/engine/snapshots.py).

export type NodeType = 'bias' | 'input' | 'output' | 'hidden'

/**
 * How a bird is being trained. 'neat' / 'gd' are the two confrontation camps
 * (also used for the pure evolution_only / gradient_only modes); 'hybrid'
 * covers the write_back / evaluate_only regimes where both forces mix.
 */
export type Camp = 'neat' | 'gd' | 'hybrid'

export interface GenomeNode {
  id: number
  type: NodeType
  activation: string
}

export interface GenomeConn {
  in: number
  out: number
  weight: number
  enabled: boolean
  innovation: number
}

export interface Genome {
  nodes: GenomeNode[]
  connections: GenomeConn[]
  inputs: number[]
  outputs: number[]
  bias: number
  fitness: number
  camp?: Camp
}

export interface Bird {
  id: number
  x: number
  y: number
  vy: number
  alive: boolean
  fitness: number
  camp?: Camp
}

export interface Pipe {
  x: number
  gapY: number
  gapH: number
}

export interface World {
  w: number
  h: number
}

export interface LeaderboardEntry {
  birdId: number
  fitness: number
  camp?: Camp
}

/** Per-camp aggregates emitted with each generation (NEAT-vs-GD confrontation). */
export interface CampStat {
  count: number
  fitnessMax: number
  fitnessMean: number
  bestBirdId: number
}

// --- Server -> client messages ------------------------------------------------

export interface FrameMsg {
  type: 'frame'
  gen: number
  tick: number
  aliveCount: number
  birds: Bird[]
  pipes: Pipe[]
  world: World | null
  selectedActivations: Record<string, number>
}

export interface GenerationMsg {
  type: 'generation'
  gen: number
  fitnessMax: number
  fitnessMean: number
  species: number
  complexity: number
  bestGenome: Genome
  bestFitness: number
  leaderboard: LeaderboardEntry[]
  camps?: Record<string, CampStat>
  winnerCamp?: Camp
}

export interface GenomeMsg {
  type: 'genome'
  birdId: number
  genome: Genome
}

export interface ConfigMsg {
  type: 'config'
  config: Record<string, unknown>
}

export interface ResetMsg {
  type: 'reset'
  ok: boolean
}

export interface ErrorMsg {
  type: 'error'
  message: string
}

export type ServerMsg =
  | FrameMsg
  | GenerationMsg
  | GenomeMsg
  | ConfigMsg
  | ResetMsg
  | ErrorMsg

// --- Client -> server ---------------------------------------------------------

export type ControlAction = 'play' | 'pause' | 'step' | 'reset'

// --- UI helpers ---------------------------------------------------------------

/** A compact per-generation row kept in history for the charts. */
export interface GenerationRow {
  gen: number
  fitnessMax: number
  fitnessMean: number
  species: number
  complexity: number
  // Per-camp curves (present in confrontation mode only).
  neatMax?: number
  neatMean?: number
  gdMax?: number
  gdMean?: number
}

export type ConnStatus = 'idle' | 'connecting' | 'open' | 'closed'

/** A minimal subset of JSON-Schema we consume to auto-build controls. */
export interface FieldSchema {
  type?: string | string[]
  title?: string
  description?: string
  default?: unknown
  minimum?: number
  maximum?: number
  enum?: unknown[]
  // Pydantic emits enums via $ref/allOf or anyOf; the Sidebar resolves those.
  allOf?: unknown[]
  anyOf?: unknown[]
  items?: unknown
  [key: string]: unknown
}

export interface ConfigSchema {
  properties: Record<string, FieldSchema>
  $defs?: Record<string, unknown>
  [key: string]: unknown
}
