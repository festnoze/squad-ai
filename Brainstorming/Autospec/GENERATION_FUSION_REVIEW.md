# Analyse — génération & fusionneur de code — 2026-07-05

Analyse du chemin **génération** (dev parallèle en worktrees) et du
**fusionneur** (merge + canari post-merge + revert) de `orchestrator/pipeline.py`,
avec l'évidence chiffrée du run réel `messagerie2` (41,5 h de logs, 6 rounds).
Complète [WORKFLOW_REVIEW.md](WORKFLOW_REVIEW.md) (revue bout-en-bout du même jour).

---

## 1. Fonctionnement observé

**Génération** (`_abuild_phase_streams` ~3135, `_abuild_work_item` ~3909) :
ordonnanceur *dataflow* — chaque slot libéré (cap `MAX_PARALLEL_DEVS=2`) est
rempli immédiatement par un item prêt (deps toutes mergées), pas de barrière de
lot. Un item = un worktree git dédié sur branche `autospec/wi-*` depuis HEAD ;
QA design (1ʳᵉ tentative backend seulement — pas de re-design au retry, bien) ;
agent dev (claude CLI) dans le worktree ; **la suite réelle fait foi**
(`_arun_pytest`/`_arun_frontend_tests` en worktree) ; footprint mesuré + gate de
périmètre avant merge ; wip commité (P2c) et **branches vertes préservées**
reprises rebasées sans re-génération (P2b, `_aresume_green_branch` +
`_averify_resumed`).

**Fusion** (`_amerge_work_item` ~4817) : merge `--no-ff` sérialisé
(`_merge_lock`) ; conflit → ① union déterministe des manifestes
(pyproject/package.json, `manifests.py`), ② sinon rebase du worktree sur HEAD
puis re-merge, ③ sinon échec → requeue **strict** (claims recalés sur les
fichiers réellement touchés, plus de co-run avec un rival possible) ; borné par
`dev_max_attempts`.

**Canari post-merge** (`_apost_merge_canary` ~4409) : la suite **complète** du
langage est rejouée sur le HEAD partagé après **chaque** merge ; rouge
« semantic » → revert `-m 1` + requeue (invariant « HEAD toujours vert ») ;
rouge « infra » → réparation env + un replay, merge conservé.

**Points forts avérés** : l'union de manifestes évite la classe de conflit
structurel la plus courante ; la préservation P2b a livré **15 reprises de
branches vertes sans re-génération** ; les compteurs de calibration (§8 :
`canary_reverts`, `merge_requeues`, `infra_retries`, `p2b_resumes`) existent
déjà pour piloter tout ça.

---

## 2. Évidence chiffrée (messagerie2, build-monitor.jsonl + interactions)

| Mesure | Valeur | Lecture |
| --- | --- | --- |
| Runs de suite (pytest + vitest) | **120** pour 17 items | ~7 suites par item ; le coût dominant du build |
| Canari : verdicts | **11/11 « semantic », 0 vert, 0 infra** | 100 % de faux positifs (tous = venv partagée détruite → 11 `env_repair invalid_venv`) ; chaque faux positif = revert d'un merge VERT + requeue + re-suites |
| `npm install/ci` | 50 | churn d'environnement (jonction, désormais corrigé) |
| Reverts / conflits (logs) | 22 / 29 | quasi tous dérivés du même problème d'env |
| Reprises P2b réussies | 15 | le mécanisme « ne jamais perdre du vert » fonctionne |
| T5-S1-S1 (helper localStorage) | **24 suites, 27,5 h, 11 appels LLM** | pour ~15 lignes de code métier, correctes dès la 1ʳᵉ tentative |
| Appels LLM totaux | 162 | la génération produit du code juste ; c'est l'infra/fusion qui le re-consomme |

Conclusion factuelle : **le générateur n'est pas le problème** (code vert prouvé
sous env sain). Les pertes viennent de la boucle *vérification → canari →
revert → requeue* quand l'environnement ment, et du fait que ces échecs
**non imputables au code consomment le budget dev**.

---

## 3. Propositions (priorisées, prémisses vérifiées dans le code)

### P0-A — Rouge sans test exécuté : réparer + rejouer TOUJOURS avant de croire au « sémantique »
`_looks_like_infra_failure` exige une **signature connue** (~5590) ; un échec
d'env inconnu (0 test exécuté, message hors liste) part en « semantic » →
revert d'un merge vert (4017). Le whack-a-mole de signatures est perdu d'avance
(on en a ajouté 2 familles en un jour : uv, vite). **Proposition** : quand
`results == {}` (aucun test n'a tourné), faire systématiquement la réparation
d'env + UN replay, même sans signature ; « semantic » seulement si le replay
reste rouge (préserve le cas ModuleNotFoundError voulu par la docstring) ou si
des tests ont réellement échoué. Coût : une suite de plus dans le pire cas ;
gain : plus aucun revert de vert sur panne d'env inconnue. *Effort S.*

### P0-B — Budget de requeue séparé : un revert/conflit ne consomme pas une tentative dev
`attempts` s'incrémente à chaque entrée (3923) et le requeue post-conflit ou
post-revert est borné par `dev_max_attempts` (4083) — or ces retries reprennent
la **branche verte préservée** (souvent sans agent dev : `dev_ran=False`) : ils
ne coûtent presque rien et ne signalent PAS un code défaillant. Avec
`dev_max_attempts=2`, **deux faux « semantic » = FAILED** (le tueur de
messagerie2). **Proposition** : symétrique d'`infra_max_retries` — un
`requeue_max` séparé (ex. 3) pour les requeues merge-conflit/canari ;
`dev_max_attempts` ne compte que les vraies re-générations (`dev_ran=True`
rouge). *Effort S-M.*

### P1-A — Canari par rafale (batch) au lieu d'une suite complète par merge
120 suites dont ~1 canari complet par merge : c'est le poste de coût n°1.
**Proposition** : sous contention (file au `_merge_lock` non vide), différer le
canari et n'en rejouer qu'UN après la rafale de merges ; s'il est rouge,
bisecter en revertant du dernier merge vers le premier (borné par la taille de
la rafale, rare car le vrai vert+vert=rouge est exceptionnel). Variante
complémentaire : 1ᵉʳ passage en sélection ciblée (`pytest --lf` / tests du
stream touché), suite complète seulement si rouge. *Effort M ; gain wall-clock
majeur.*

### P1-B — Ne pas garder un slot dev pendant merge + canari
Le worker occupe son slot (`running`, cap 2) durant `MERGE_WAIT` + merge +
canari — sérialisés par `_merge_lock` de toute façon. Avec cap=2, pendant un
canari de 2-3 min, 50 % de la capacité dort. **Proposition** : ne compter dans
le cap que les items en phase dev/verify (exclure les stages
MERGE_WAIT/MERGING/CANARY du décompte de remplissage), avec un plafond dur
cap+1 pour rester borné. *Effort S-M.*

### P1-C — Ordonnancer les feuilles à fort fan-out d'abord
Le remplissage suit `graph.order` (topologique, 3246) sans prioriser. T5-S1-S1
bloquait transitivement 20+ items mais n'était pas priorisé. **Proposition** :
parmi les items prêts, trier par nombre de dépendants transitifs décroissant
(puis priorité déclarée) — le chemin critique d'abord ; et accorder +1
tentative dev aux items dont le fan-out dépasse un seuil (ex. 5) : leur échec
coûte l'itération. *Effort S.*

### P2-A — 2ᵉ conflit de merge : mode SOLO au lieu de FAILED
Aujourd'hui : 2ᵉ conflit → FAILED (docstring 3915, `_conflict_retry_ids`).
**Proposition** : dernier recours avant FAILED — attendre le drain complet des
items en vol, puis rebuild SEUL sur le HEAD final : un item sans voisin ne peut
plus conflicter. C'est un « 3ᵉ essai à vide » bon marché comparé à un FAILED
qui gèle tous les dépendants. *Effort M.*

### P2-B — Cache npm partagé pour les installs hermétiques
Les worktrees font désormais un vrai `npm ci` (50 installs observés).
**Proposition** : `--cache <workspace>/_npm-cache --prefer-offline` pour
mutualiser les téléchargements entre worktrees sans repartager `node_modules`.
*Effort S.*

### P3 — Observabilité de la boucle de fusion
Les compteurs §8 existent ; exposer dans la rétro le ratio « suites exécutées /
items livrés » et « verdicts canari par type » (11/11 semantic aurait crié au
scandale dès le round 1). *Effort S.*

---

## 4. Synthèse gestion des échecs

Règle directrice qui ressort de l'évidence : **ne débiter le budget dev que
pour un échec imputable au code généré.** Env cassé → réparer/rejouer (P0-A),
requeue de fusion → budget dédié (P0-B), item critique → budget bonifié (P1-C),
dernier recours → solo (P2-A). Le générateur, lui, produit du code juste — le
harnais doit arrêter de le lui faire payer.

> Note : l'analyse multi-agents initiale est morte sur la limite de session
> Claude (reset 17 h) ; l'analyse a été menée en direct sur le code
> (`pipeline.py`, `streams.py`, `independence.py`, `manifests.py`) et les logs
> réels. Aucune proposition n'est implémentée ici — voir la priorisation pour
> choisir.
