// Shared camp + mode presentation constants, used by the canvas, charts,
// leaderboard and status bar so the NEAT-vs-GD color language stays coherent.

import type { Camp } from './types'

/** Concrete hex values (canvas + recharts cannot consume CSS variables). */
export const CAMP_COLORS: Record<Camp, string> = {
  neat: '#4fd1c5', // teal — evolution
  gd: '#f6a04d', // orange — gradient descent
  hybrid: '#b48cff', // violet — both forces mixed
}

export const CAMP_LABELS: Record<Camp, string> = {
  neat: 'NEAT',
  gd: 'GD',
  hybrid: 'Hybride',
}

export interface ModeInfo {
  value: string
  label: string
  /** One-line explanation shown in the status bar / button tooltips. */
  title: string
}

export const MODES: ModeInfo[] = [
  {
    value: 'evolution_only',
    label: 'Évolution seule',
    title:
      'Neuroévolution pure (NEAT) : sélection, croisement, mutation, spéciation. Pas de gradient.',
  },
  {
    value: 'gradient_only',
    label: 'Réseau seul',
    title:
      'Gradient descent pur : topologie figée, entraînée par imitation. Aucune évolution (ni sélection ni mutation).',
  },
  {
    value: 'write_back',
    label: 'Hybride W-B',
    title: 'NEAT + GD (lamarckien) : les poids appris repassent dans le génome.',
  },
  {
    value: 'evaluate_only',
    label: 'Hybride E-O',
    title:
      'NEAT + GD (baldwinien) : le GD note la fitness, le génome de naissance est transmis.',
  },
  {
    value: 'confrontation',
    label: '⚔ Confrontation',
    title:
      'Duel NEAT vs GD : la population est scindée (ratio GD réglable) en un camp NEAT (évolution pure) ' +
      'et un camp GD (topologie figée, descente de gradient pure). Mêmes tuyaux, deux lignées étanches — ' +
      'le champion est 100 % NEAT ou 100 % GD.',
  },
]

export function modeInfo(mode: string | undefined): ModeInfo | undefined {
  return MODES.find((m) => m.value === mode)
}
