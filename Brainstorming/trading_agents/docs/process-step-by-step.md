# Trading Agents — Process pas à pas

Guide complet du pipeline actuel, de la récupération de données jusqu'à l'évolution génétique de stratégies.

---

## Vue d'ensemble du pipeline

```
 1. Données          Téléchargement + cache local (yfinance → Parquet)
      ↓
 2. Backtest simple  MA crossover sur un actif (VectorBT)
      ↓
 3. Sweep paramétrique  Balayage vectorisé de toutes les combinaisons MA
      ↓
 4. Walk-Forward     Optimisation RSI+BB+SL/TP par fenêtres glissantes
      ↓
 5. Détection de régime  ADX + Hurst → trending / reverting / uncertain
      ↓
 6. Stratégie adaptive   Switching automatique selon le régime
      ↓
 7. Évolution génétique  DEAP découvre des stratégies from scratch (GP)
      ↓
 8. Scoring & validation  Score composite + Monte Carlo + multi-actifs
      ↓
 9. Optimisation hyper    Optuna optimise les hyperparamètres du GP
```

---

## Étape 1 — Récupération des données

**Fichier :** `src/data/provider.py`

Le provider télécharge les données OHLCV via **yfinance** et les cache localement en fichiers **Parquet** dans `data/`.

**Fonctionnement :**
1. Un appel à `load_price_data("AAPL", interval="1h", start="2024-06-01", end="2026-05-29")` construit un chemin de cache déterministe : `AAPL_1h_2024-06-01_2026-05-29.parquet`
2. Si le fichier existe → chargement immédiat depuis le cache
3. Sinon, recherche d'un fichier **couvrant** (même symbole/intervalle, plage de dates plus large) → extraction d'un sous-ensemble
4. En dernier recours → téléchargement via yfinance, sauvegarde en Parquet

**Intervalles supportés :** `1m` (7j max), `5m/15m/30m` (60j max), `1h` (730j), `1d/1w` (illimité)

**Mapping fréquence :** Chaque intervalle est converti en alias pandas pour VectorBT (`"1h"` → `"1h"`, `"1d"` → `"1D"`, etc.)

---

## Étape 2 — Backtest simple (MA Crossover)

**Fichier :** `examples/first_backtest.py`
**Moteur :** `src/backtesting/engine.py`

Premier test : croisement de moyennes mobiles sur un actif unique.

**Déroulement :**
1. Charger les prix via `load_price_data()`
2. Calculer la MA rapide (ex: 10 barres) et la MA lente (ex: 50 barres) via `vbt.MA.run()`
3. Signaux d'**entrée** = MA rapide croise au-dessus de la MA lente
4. Signaux de **sortie** = MA rapide croise en-dessous
5. Exécuter le backtest : `vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, fees=0.001)`
6. Afficher les résultats : Total Return, Sharpe Ratio, Max Drawdown, Win Rate, Profit Factor
7. Générer un graphique Plotly (prix + signaux, valeur du portefeuille vs Buy & Hold) et sauvegarder en PNG

**Moteur de backtest (`engine.py`) :**
- `BacktestConfig` : dataclass de configuration (symbole, intervalle, dates, capital, frais)
- `BacktestResult` : résultat structuré (portfolio VBT, prix, signaux, nom de l'actif, devise)
- `run_backtest()` : lance le backtest, récupère les métadonnées ticker (nom, devise)
- `build_plot()` : graphique à 2 panneaux (prix+signaux en haut, portefeuille vs benchmarks en bas), supporte des courbes de comparaison (`ComparisonCurve`)

---

## Étape 3 — Sweep paramétrique vectorisé

**Fichier :** `examples/parameter_sweep.py`

Balayage exhaustif de toutes les combinaisons de fenêtres MA rapide/lente.

**Déroulement :**
1. Définir les plages : fast = [5, 10, 15, ..., 50], slow = [20, 30, 40, ..., 200]
2. Calculer **toutes les MAs en un seul appel** : `vbt.MA.run(price, window=all_windows)` — la vectorisation NumPy rend ça quasi-instantané
3. Pour chaque paire (fast, slow) valide (fast < slow) :
   - Extraire les signaux d'entrée/sortie (front montant du croisement)
   - Lancer un backtest rapide
   - Stocker le Sharpe ratio dans une matrice
4. Identifier la meilleure combinaison
5. Générer une **heatmap Sharpe** (axe X = slow MA, axe Y = fast MA, couleur = Sharpe)
6. Relancer un backtest complet avec la meilleure paire et comparer

**Résultat typique :** 10 × 19 = 190 combinaisons évaluées en quelques secondes.

---

## Étape 4 — Walk-Forward Optimization (RSI + BB + SL/TP)

**Fichier :** `examples/walk_forward_optimizer.py`

Optimisation par fenêtres glissantes avec stratégie multi-indicateurs.

**Stratégie :**
- **Entrée :** RSI < seuil_bas ET prix < bande de Bollinger inférieure
- **Sortie :** RSI > seuil_haut ET prix > bande de Bollinger supérieure
- **Stop-Loss / Take-Profit** : appliqués automatiquement par VectorBT

**Process Walk-Forward :**
1. Paramètres de fenêtre : train = 180j, test = 60j, pas = 60j
2. Pour chaque fenêtre :
   - **Phase TRAIN** : sweep de toutes les combinaisons (RSI windows × seuils × BB windows × BB alpha × SL × TP) sur la période d'entraînement. Score composite = 40% Sharpe + 30% Sortino + 30% Profit Factor
   - **Phase TEST (OOS)** : appliquer les meilleurs paramètres sur la fenêtre de test (jamais vue pendant l'optimisation)
3. **Stitching** : assembler les signaux de toutes les fenêtres test en une série continue
4. Backtest final sur la série complète assemblée
5. Comparaison avec les stratégies MA des exemples précédents

**Intérêt :** Évite le surapprentissage (overfitting). Chaque fenêtre test est indépendante de l'optimisation.

---

## Étape 5 — Détection de régime de marché

**Fichier :** `src/evaluation/regime.py`

Classification du marché en 3 régimes à chaque instant.

**Indicateurs :**
- **ADX (Average Directional Index)** : mesure la **force** du trend (0-100), pas sa direction
  - ADX > 25 = trend fort
  - ADX < 20 = pas de trend
  - Calculé avec l'EMA de Wilder (alpha = 1/window)
- **Exposant de Hurst** : mesure la persistance/antipersistance
  - H > 0.5 = persistent (trending)
  - H = 0.5 = marche aléatoire
  - H < 0.5 = anti-persistent (mean-reverting)
  - Calculé par variance des différences retardées sur une fenêtre glissante

**Régimes :**
| Régime | Condition |
|--------|-----------|
| **TRENDING** | ADX > 25 ET Hurst > 0.40 |
| **REVERTING** | ADX < 20 ET Hurst < 0.35 |
| **UNCERTAIN** | Tout le reste |

`compute_regime_series(df)` retourne un DataFrame avec colonnes `adx`, `hurst`, `regime` pour chaque barre.

---

## Étape 6 — Stratégie adaptative (regime-switching)

**Fichier :** `examples/adaptive_strategy.py`

Combine la détection de régime avec des stratégies spécialisées.

**Logique :**
- **TRENDING** → MA crossover (trend-following)
  - Entrée : MA(20) croise au-dessus de MA(50) OU entrée en régime trending avec MAs déjà haussières
  - Sortie : MA(20) croise sous MA(50)
- **REVERTING** → RSI + Bollinger Bands (mean-reversion)
  - Entrée : RSI < 30 ET prix < BB lower
  - Sortie : RSI > 70 ET prix > BB upper
- **UNCERTAIN** → Cash (aucun trade)
  - Sortie forcée de toute position ouverte lors de la transition vers UNCERTAIN

**Visualisation :** Graphique à 3 panneaux :
1. Prix + signaux avec bandes colorées par régime (vert = trending, orange = reverting)
2. Indicateurs ADX et Hurst avec seuils
3. Valeur du portefeuille — comparaison de toutes les stratégies

---

## Étape 7 — Évolution génétique de stratégies (GP)

**Fichiers :** `src/agent/grammar.py`, `src/agent/fitness.py`, `src/agent/evolution.py`
**Exemple :** `examples/gp_strategy_evolution.py`

La programmation génétique (GP) via DEAP **découvre automatiquement** des règles de trading.

### 7.1 — Grammaire (`grammar.py`)

Vocabulaire de primitives que le GP combine en arbres de décision :

| Type | Exemples |
|------|----------|
| **Prix** | Close, High, Low |
| **Indicateurs** (par fenêtre 7/10/14/20/30/50) | SMA, RSI, Bollinger Upper/Lower, ATR |
| **Alpha factors** | ROC (Rate of Change), VPT (Volume-Price Trend), PSR (Price/SMA Ratio), Volatility Ratio, Higher High, Lower Low, Volume Spike, MACD Histogram |
| **Comparaisons** | GT, LT, CrossAbove, CrossBelow |
| **Logique** | AND, OR, NOT |
| **Constantes** | 20, 25, 30, 35, 50, 65, 70, 75, 80 |

Chaque primitive est typée (`SeriesFloat` ou `SeriesBool`) et wrappée dans `_safe()` pour capturer les erreurs pendant l'évolution.

**Score de complexité** (`tree_complexity_score`) :
- Base = nombre de nœuds
- +2 par indicateur imbriqué (ex: `SMA(RSI(...))` — presque toujours du bruit)
- +3 si l'arbre ne touche jamais aux prix réels

### 7.2 — Fitness (`fitness.py`)

**Mode pair (entry/exit séparés) :** Deux arbres GP indépendants — un pour les entrées, un pour les sorties.

**Walk-forward interne :**
1. Diviser le training set en K fenêtres glissantes (train_pct = 70%)
2. Pour chaque fenêtre : burn-in sur la partie in-sample (warmup des indicateurs), scoring uniquement sur la partie OOS
3. Fitness = **moyenne des Sharpe OOS** − pénalité de complexité

Cela empêche le GP de mémoriser les données d'entraînement.

### 7.3 — Boucle d'évolution (`evolution.py`)

**Individu** = `[EntryTree, ExitTree]` — deux arbres DEAP partageant la même grammaire.

**Opérateurs génétiques :**
- **Sélection par tournoi avec diversité** : cap sur le nombre d'individus de la même "famille" (signature = ensemble de primitives utilisées). Les doublons sont remplacés par des individus de familles sous-représentées.
- **Croisement** : échange de sous-arbres entre entry/entry et exit/exit (pas de mélange). Revert si la profondeur dépasse `max_depth`.
- **Mutation** : choix aléatoire d'un des deux arbres, remplacement d'un sous-arbre par un nouveau généré. Revert si trop profond.

**Validation :** Les top N stratégies du Hall of Fame sont décodées et testées sur :
- **In-sample** (données d'entraînement)
- **Out-of-sample** (données de test, jamais vues)

Un indicateur d'overfitting est calculé : si `test_sharpe < train_sharpe × 0.3`, la stratégie est flaggée.

---

## Étape 8 — Scoring et validation statistique

### 8.1 — Score composite (`src/evaluation/scoring.py`)

Évalue les stratégies selon 4 axes pondérés :

| Composante | Poids | Description |
|------------|-------|-------------|
| **Return Score** | 25% | `log(1 + return) × 10`, plafonné à 10. L'échelle log empêche les retours explosifs de dominer |
| **Risk Score** | 30% | Pénalise le drawdown > 50%, récompense les ratios Calmar et Sortino |
| **Efficiency Score** | 25% | Retour par unité d'exposition au marché. Favorise les stratégies "peu au marché mais rentables" |
| **Stability Score** | 20% | Temps hors drawdown, taux de victoire, profit factor |

**Score final** : somme pondérée normalisée entre 0 et 10.

**Ranking** : `rank_strategies()` trie une liste de stratégies par score composite décroissant.

**Analyse de drawdown** : `drawdown_analysis()` identifie chaque période de drawdown > 5%, avec profondeur, durée, et temps de récupération.

### 8.2 — Tests de Monte Carlo (`src/evaluation/montecarlo.py`)

3 tests indépendants pour valider qu'une stratégie n'est pas due au hasard :

1. **Test de permutation** (1000 simulations)
   - Mélanger aléatoirement les rendements journaliers
   - Calculer le Sharpe de chaque série mélangée
   - p-value = % de Sharpe simulés ≥ Sharpe réel
   - Significatif si p < 0.05

2. **Bootstrap CI** (1000 resamples)
   - Rééchantillonner les rendements avec remplacement
   - Calculer les intervalles de confiance à 95% pour le retour total, le Sharpe, et le max drawdown

3. **Test d'entrées aléatoires** (1000 simulations)
   - Générer des signaux d'entrée/sortie aléatoires (même nombre de trades, même durée moyenne)
   - Comparer la stratégie réelle à la distribution des traders aléatoires
   - "La stratégie bat X% des traders aléatoires"

**Verdict final :**
- `SIGNIFICANT` : permutation p < 0.05 ET random entry p < 0.10
- `MARGINAL` : permutation p < 0.10 OU random entry p < 0.20
- `NOT_SIGNIFICANT` : aucun des deux

### 8.3 — Validation multi-actifs (`src/evaluation/multiasset.py`)

Teste la même stratégie sur plusieurs actifs (BTC, ETH, AAPL, GOOGL, MSFT...) pour vérifier qu'elle **généralise**.

**Note de robustesse :**
| Grade | Condition |
|-------|-----------|
| **A** | ≥ 80% rentable, Sharpe moyen > 0.5, écart-type Sharpe < 1.0 |
| **B** | ≥ 60% rentable, Sharpe moyen > 0.3 |
| **C** | ≥ 40% rentable, Sharpe moyen > 0 |
| **D** | ≥ 20% rentable |
| **F** | < 20% rentable |

**Signal builders réutilisables :** Factories pour créer des stratégies paramétrées :
- `build_ma_crossover_builder(fast, slow)` → callable `(price, df) → (entries, exits)`
- `build_rsi_bb_builder(rsi_window, rsi_lo, rsi_hi, bb_window, bb_alpha)` → idem

### 8.4 — Allocateur multi-stratégies (`src/evaluation/allocator.py`)

Combine plusieurs stratégies en un portefeuille unique avec des **poids dynamiques** :

**Calcul des poids (par jour) :**
- **50% Affinité au régime** : chaque stratégie déclare son efficacité par régime (ex: MA crossover → trending = 0.7, reverting = 0.1)
- **30% Performance rolling** : Sharpe ratio glissant — les stratégies performantes récemment sont sur-pondérées
- **20% Pénalité drawdown** : les stratégies en drawdown > 10% sont sous-pondérées

Le portefeuille combiné est construit à partir des rendements pondérés quotidiens.

---

## Étape 9 — Optimisation des hyperparamètres GP (Optuna)

**Fichier :** `src/agent/optimizer.py`

Utilise **Optuna** (TPE sampler) pour trouver les meilleurs hyperparamètres du GP.

**Espace de recherche :**
| Paramètre | Plage |
|-----------|-------|
| `pop_size` | 50 – 300 (pas de 50) |
| `n_gen` | 10 – 50 (pas de 5) |
| `max_depth` | 4 – 8 |
| `complexity_penalty` | 0.01 – 0.10 |
| `cx_prob` (crossover) | 0.5 – 0.9 |
| `mut_prob` (mutation) | 0.1 – 0.4 |
| `n_splits` (walk-forward) | 2 – 5 |

**Process :**
1. Pour chaque trial Optuna :
   - Sampler un jeu d'hyperparamètres
   - Lancer un cycle complet : setup → évolution GP → validation OOS
   - Retourner le Sharpe OOS comme score
2. Après N trials : re-lancer le meilleur trial pour capturer les détails de la stratégie
3. Retourner : `best_params`, `best_score`, `best_strategy`, statistiques de l'optimisation

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Données historiques | yfinance |
| Cache local | Parquet (pandas) |
| Moteur de backtest | VectorBT |
| Graphiques | Plotly (sauvegarde PNG via kaleido) |
| Programmation génétique | DEAP |
| Optimisation hyper | Optuna |
| Broker (futur) | Interactive Brokers via `ib_insync` |
| Agent LLM (futur) | Anthropic (Claude) |

---

## Exécution

Depuis la racine du projet (`c:\Dev\squad-ai\Brainstorming`) :

```bash
# Activer le venv
.venv\Scripts\activate

# Ou via uv
uv run python trading_agents/examples/first_backtest.py
uv run python trading_agents/examples/parameter_sweep.py
uv run python trading_agents/examples/walk_forward_optimizer.py
uv run python trading_agents/examples/adaptive_strategy.py
uv run python trading_agents/examples/gp_strategy_evolution.py
```

Les exemples s'enchaînent en complexité croissante. Chaque script est autonome et compare ses résultats avec les stratégies précédentes.
