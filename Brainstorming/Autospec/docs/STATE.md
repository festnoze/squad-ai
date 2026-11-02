# Autospec : état courant

Document d'état unique de la refonte v2 (principe P6 de `docs/REFONTE_V2.md`). Chaque session de
travail ajoute une entrée au journal, en tête.

## Où on en est

- Phases 0, 1 et 2 faites : banc opérationnel, noyau v2 séquentiel pour les profils lib, cli et api,
  mesuré sur B1 à B3 (résultats et lecture : `docs/REFONTE_V2.md` section 11, tableau :
  `docs/bench/README.md`).
- Prochaine étape proposée : phase 3 (fullstack, B4) et B5, pour trouver où le harness nu échoue.
- Branche de travail : `refonte-v2`. Référence v1 : tag `v1-ref` et branche `v1-archive` (`5dea3e71`).
- Contrats des modules du noyau : `docs/v2/CONTRACTS.md`.

## Journal

### 2026-11-02 (suite) : premiers runs réels

- Noyau v2 intégré : 291 tests (`backend/tests_v2`, ~4 min, dont le pipeline de bout en bout avec
  de vrais uv et git), banc avec oracles validés sur des produits de référence (`backend/bench`).
- Runs : v2 sur B1, B2, B3 tous corrects à l'oracle ; harness nu identique en qualité, dix fois
  moins cher ; v1 bloquée par l'absence de Docker.
- Défauts trouvés par les runs et corrigés : test d'acceptance déjà vert grâce aux stories
  précédentes (accepté et journalisé), story entièrement satisfaite (marquée terminée sans dev),
  tests qui ne référencent pas le paquet (rejetés), faille conftest/pytest (rejetée).
- Reprise réelle validée (`python -m autospec.core resume <ws>`).


### 2026-11-02 : démarrage de la v2

- Décisions sur les 8 questions ouvertes : `docs/REFONTE_V2.md` section 10.
- Spike confinement : `claude -p` natif sous liste blanche validé (23 s, 0,04 $, `tasklist` refusé).
- Noyau v2 en construction : contrats partagés (`models`, `ports`, `jsonx`, `procs`, `settings`),
  machine à états, persistance, pipeline, CLI, agents scriptés ; modules feuilles et banc écrits
  en parallèle par quatre sous-agents sur des fichiers distincts.
