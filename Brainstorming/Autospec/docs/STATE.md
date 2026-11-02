# Autospec : état courant

Document d'état unique de la refonte v2 (principe P6 de `docs/REFONTE_V2.md`). Chaque session de
travail ajoute une entrée au journal, en tête.

## Où on en est

- Phase en cours : **0 (baseline et spikes) et 1 (noyau séquentiel lib/cli)**.
- Branche de travail : `refonte-v2`. Référence v1 : tag `v1-ref` et branche `v1-archive` (`5dea3e71`).
- Contrats des modules du noyau : `docs/v2/CONTRACTS.md`.

## Journal

### 2026-11-02 : démarrage de la v2

- Décisions sur les 8 questions ouvertes : `docs/REFONTE_V2.md` section 10.
- Spike confinement : `claude -p` natif sous liste blanche validé (23 s, 0,04 $, `tasklist` refusé).
- Noyau v2 en construction : contrats partagés (`models`, `ports`, `jsonx`, `procs`, `settings`),
  machine à états, persistance, pipeline, CLI, agents scriptés ; modules feuilles et banc écrits
  en parallèle par quatre sous-agents sur des fichiers distincts.
