# Banc de mesure Autospec

Généré par `python -m bench.report` depuis les JSON de ce dossier. Métriques : docs/REFONTE_V2.md section 5.2 (M1 complétion sans intervention, M2 durée, M3 coût, M4 appels agents, M5 suite du produit en environnement propre, M6 oracle caché, M7 smoke).

## 2026-11-02

| Projet | Config | Modèle | M1 | M2 | M3 | M4 | M5 | M6 | M7 | Commit |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | A v1 | sonnet | non | 0.0 min | 0.00 $ |  | 0/0 | 0/12 | oui | bd600f04 |
| B1 | B harness nu | sonnet | oui | 0.5 min | 0.04 $ | 1 | 15/15 vert | 12/12 | oui | bd600f04 |
| B1 | C v2 | sonnet | oui | 4.5 min | 0.38 $ | 8 | 37/37 vert | 12/12 | oui | 06b75edc |
| B2 | A v1 | sonnet | non | 0.0 min | 0.00 $ |  | 0/0 | 1/10 | non | bd600f04 |
| B2 | B harness nu | sonnet | oui | 1.0 min | 0.08 $ | 1 | 12/12 vert | 10/10 | oui | bd600f04 |
| B2 | C v2 | sonnet | non | 7.2 min | 0.62 $ | 11 | 31/31 vert | 10/10 | oui | bd600f04 |
| B2 | c-resume | sonnet | n/a |  |  |  | 34/34 vert | 10/10 | oui | bd600f04 |
| B3 | B harness nu | sonnet | oui | 0.8 min | 0.08 $ | 1 | 13/13 vert | 15/15 | oui | 04e85264 |
| B3 | C v2 | sonnet | oui | 12.9 min | 0.74 $ | 11 | 43/43 vert | 15/15 | oui | 04e85264 |
