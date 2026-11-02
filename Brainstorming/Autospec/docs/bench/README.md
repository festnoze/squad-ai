# Banc de mesure Autospec

Généré par `python -m bench.report` depuis les JSON de ce dossier. Métriques : docs/REFONTE_V2.md section 5.2 (M1 complétion sans intervention, M2 durée, M3 coût, M4 appels agents, M5 suite du produit en environnement propre, M6 oracle caché, M7 smoke).

## 2026-11-02

| Projet | Config | Modèle | M1 | M2 | M3 | M4 | M5 | M6 | M7 | Commit |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | A v1 | sonnet | non | 0.0 min | 0.00 $ |  | 0/0 | 0/12 | oui | bd600f04 |
| B1 | B harness nu | sonnet | oui | 0.5 min | 0.04 $ | 1 | 15/15 vert | 12/12 | oui | bd600f04 |
| B1 | B harness nu | sonnet | oui | 0.6 min | 0.04 $ | 1 | 15/15 vert | 12/12 | oui | 836de199 |
| B1 | C v2 | sonnet | oui | 4.5 min | 0.38 $ | 8 | 37/37 vert | 12/12 | oui | 06b75edc |
| B1 | C v2 | sonnet | oui | 3.5 min | 0.29 $ | 7 | 38/38 vert | 12/12 | oui | 836de199 |
| B1 | C v2 | sonnet | non | 1.2 min | 0.13 $ | 2 | 1/15 | 0/12 | oui | 85c7e437 |
| B1 | C v2 | sonnet | oui | 1.4 min | 0.18 $ | 3 | 28/28 vert | 12/12 | oui | 530cf69e |
| B2 | A v1 | sonnet | non | 0.0 min | 0.00 $ |  | 0/0 | 1/10 | non | bd600f04 |
| B2 | B harness nu | sonnet | oui | 1.0 min | 0.08 $ | 1 | 12/12 vert | 10/10 | oui | bd600f04 |
| B2 | B harness nu | sonnet | oui | 1.0 min | 0.10 $ | 1 | 18/18 vert | 10/10 | oui | 836de199 |
| B2 | C v2 | sonnet | non | 7.2 min | 0.62 $ | 11 | 31/31 vert | 10/10 | oui | bd600f04 |
| B2 | C v2 | sonnet | oui | 5.7 min | 0.54 $ | 9 | 31/31 vert | 10/10 | oui | 836de199 |
| B2 | C v2 | sonnet | oui | 2.5 min | 0.26 $ | 3 | 19/19 vert | 10/10 | oui | 85c7e437 |
| B2 | c-resume | sonnet | n/a |  |  |  | 34/34 vert | 10/10 | oui | bd600f04 |
| B3 | B harness nu | sonnet | oui | 0.8 min | 0.08 $ | 1 | 13/13 vert | 15/15 | oui | 04e85264 |
| B3 | B harness nu | sonnet | oui | 0.8 min | 0.09 $ | 1 | 12/12 vert | 15/15 | oui | 836de199 |
| B3 | C v2 | sonnet | oui | 12.9 min | 0.74 $ | 11 | 43/43 vert | 15/15 | oui | 04e85264 |
| B3 | C v2 | sonnet | oui | 20.1 min | 0.89 $ | 14 | 58/58 vert | 15/15 | oui | 836de199 |
| B3 | C v2 | sonnet | oui | 2.9 min | 0.26 $ | 3 | 17/17 vert | 15/15 | oui | 85c7e437 |
| B4 | B harness nu | sonnet | oui | 1.8 min | 0.11 $ | 1 | 8/8 vert | 8/8 | oui | 964d808a |
| B4 | C v2 | sonnet | oui | 8.2 min | 0.32 $ | 3 | 20/20 vert | 8/8 | oui | 964d808a |
| B5 | B harness nu | sonnet | oui | 16.3 min | 2.29 $ | 1 | 165/165 vert | 33/57 (22 NOT_AUTOMATED) | oui | 964d808a |
