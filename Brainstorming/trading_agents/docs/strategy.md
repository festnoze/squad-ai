# Trading Agents -- Documentation Strategie

## Table des matieres

1. [Vue fonctionnelle](#1-vue-fonctionnelle)
2. [Architecture technique](#2-architecture-technique)
3. [Modules en detail](#3-modules-en-detail)
4. [Exemples implementes](#4-exemples-implementes)
5. [Resultats et enseignements](#5-resultats-et-enseignements)
6. [Feuille de route](#6-feuille-de-route)

---

## 1. Vue fonctionnelle

### 1.1 Objectif

Construire un systeme de trading algorithmique **auto-ameliorant** qui :

- Genere autonomement des strategies de trading
- Les teste sur des donnees historiques via backtesting
- Evalue leur performance avec des metriques de risque/rendement
- Itere pour decouvrir des strategies plus performantes
- Detecte automatiquement le regime de marche pour adapter son approche

### 1.2 Chaine de valeur

```
Donnees de marche -> Detection de regime -> Selection de strategie -> Backtest -> Evaluation -> Iteration
```

Le systeme ne se contente pas d'optimiser des parametres (combien de jours pour une moyenne mobile ?). Il explore **l'espace des strategies** lui-meme : quels indicateurs combiner, quelles regles logiques appliquer, quel type de strategie utiliser selon le contexte.

### 1.3 Types de strategies implementees

| Strategie | Famille | Principe | Quand l'utiliser |
|-----------|---------|----------|------------------|
| **MA Crossover** | Trend-following | Acheter quand la MA rapide passe au-dessus de la MA lente | Marche en tendance (ADX > 25, Hurst > 0.40) |
| **RSI + Bollinger Bands** | Mean-reversion | Acheter en survente (RSI bas + prix sous BB), vendre en surachat | Marche range-bound (ADX < 20, Hurst < 0.35) |
| **Adaptive** | Hybride | Detecte le regime et bascule automatiquement entre trend-following et mean-reversion | Tout marche |
| **GP Evolution** | Decouverte | Programmation genetique : fait evoluer des arbres de regles de trading | Exploration de nouvelles strategies |

### 1.4 Detection de regime de marche

Le systeme classifie chaque jour en 3 regimes :

- **TRENDING** : Tendance forte (haussiere ou baissiere). L'ADX est eleve (> 25) et l'exposant de Hurst montre de la persistance (> 0.40). Strategie : trend-following.
- **REVERTING** : Marche range-bound, les prix oscillent autour d'une moyenne. ADX faible (< 20) et Hurst bas (< 0.35). Strategie : mean-reversion.
- **UNCERTAIN** : Regime mixte ou transitoire. Le systeme reste en cash pour eviter les faux signaux.

### 1.5 Metriques d'evaluation

Chaque strategie est evaluee sur :

| Metrique | Signification | Bon seuil |
|----------|---------------|-----------|
| **Sharpe Ratio** | Rendement ajuste du risque (annualise) | > 1.0 |
| **Sortino Ratio** | Comme Sharpe mais ne penalise que la volatilite negative | > 1.5 |
| **Max Drawdown** | Perte maximale depuis un pic | < -20% |
| **Win Rate** | Pourcentage de trades gagnants | > 50% |
| **Profit Factor** | Gains bruts / Pertes brutes | > 1.5 |
| **Nombre de trades** | Frequence de trading | Ni trop bas (< 5) ni trop haut |

### 1.6 Garde-fous anti-overfitting

L'overfitting (trouver des patterns dans le bruit) est le risque principal. Mesures en place :

1. **Walk-forward validation** : optimiser sur une fenetre glissante (6 mois), valider sur la fenetre suivante (2 mois), avancer et recommencer.
2. **Split train/test** : les strategies GP sont entrainees sur 2020-2024 et validees sur 2025-2026 (donnees jamais vues).
3. **Penalite de complexite** : les strategies avec beaucoup de noeuds sont penalisees (-0.02 Sharpe par noeud). Les strategies simples sont preferees.
4. **Score composite** : ne pas se fier au Sharpe seul. Score = 40% Sharpe + 30% Sortino + 30% Profit Factor normalise.
5. **Detection d'overfit** : si le Sharpe test < 30% du Sharpe train, la strategie est flaggee comme overfit.

---

## 2. Architecture technique

### 2.1 Stack technologique

| Composant | Technologie | Role |
|-----------|-------------|------|
| **Backtesting** | VectorBT | Execution vectorisee de strategies, sweep de parametres |
| **Donnees** | yfinance + cache Parquet | Telechargement et persistance des donnees OHLCV |
| **Detection regime** | ADX + Hurst (custom) | Classification trending/reverting/uncertain |
| **Evolution** | DEAP (Genetic Programming) | Decouverte de strategies via programmation genetique |
| **Visualisation** | Plotly + Kaleido | Graphiques interactifs, export PNG |
| **Broker (futur)** | Interactive Brokers via ib_insync | Paper trading puis trading reel |

### 2.2 Structure du projet

```
trading_agents/
├── CLAUDE.md                    # Instructions projet pour Claude
├── docs/
│   └── strategy.md             # Ce document
├── data/                        # Cache Parquet des donnees de marche
│   ├── BTC-USD_1d_2020-01-01_2026-05-31.parquet
│   └── GOOGL_1h_2024-06-01_2026-05-29.parquet
│
├── src/
│   ├── data/
│   │   └── provider.py          # Telechargement + cache Parquet
│   ├── backtesting/
│   │   └── engine.py            # Config, backtest, plotting, resultats
│   ├── evaluation/
│   │   └── regime.py            # Detecteur de regime ADX + Hurst
│   └── agent/
│       ├── grammar.py           # Grammaire GP (primitives DEAP)
│       ├── fitness.py           # Fonction fitness (arbre -> score)
│       └── evolution.py         # Boucle evolutive DEAP
│
├── examples/
│   ├── first_backtest.py        # Ex1: MA crossover simple
│   ├── parameter_sweep.py       # Ex2: Sweep vectorise + heatmap
│   ├── walk_forward_optimizer.py # Ex3: Walk-forward RSI+BB
│   ├── adaptive_strategy.py     # Ex4: Strategie adaptive par regime
│   └── gp_strategy_evolution.py # Ex5: Evolution genetique DEAP
│
├── strategies/                   # Configs de strategies (JSON/YAML)
├── results/                      # Logs de backtest
└── tests/
```

### 2.3 Flux de donnees

```
                    yfinance
                       │
                       ▼
              ┌────────────────┐
              │  provider.py   │ Telecharge ou charge depuis cache Parquet
              │  load_price_data()
              └───────┬────────┘
                      │ DataFrame OHLCV
          ┌───────────┼───────────────┐
          ▼           ▼               ▼
    ┌──────────┐ ┌──────────┐ ┌──────────────┐
    │ engine.py│ │ regime.py│ │ grammar.py   │
    │ Backtest │ │ ADX+Hurst│ │ Primitives GP│
    └────┬─────┘ └────┬─────┘ └──────┬───────┘
         │            │              │
         ▼            ▼              ▼
    ┌──────────┐ ┌──────────┐ ┌──────────────┐
    │ Resultats│ │ Regimes  │ │ fitness.py   │
    │ + Plots  │ │ par jour │ │ Evaluation   │
    └──────────┘ └──────────┘ └──────┬───────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │ evolution.py │
                              │ Boucle DEAP  │
                              └──────────────┘
```

---

## 3. Modules en detail

### 3.1 `src/data/provider.py` -- Couche donnees

**Responsabilite** : telecharger les donnees OHLCV via yfinance et les cacher localement en Parquet.

**Fonctions cles** :

- `load_price_data(symbol, interval, start, end)` : point d'entree principal. Verifie le cache, telecharge si necessaire.
- `_find_covering_cache(symbol, interval, start, end)` : si un fichier cache couvre une plage plus large que demande, il est charge et slice. Evite les re-telechargements pour des sous-periodes.
- `get_ticker_info(symbol)` : recupere le nom de l'actif et la devise via yfinance.
- `INTERVAL_TO_FREQ` : mapping des intervalles yfinance ("1h", "1d") vers les frequences VectorBT ("1h", "1D").

**Cache** : fichiers Parquet dans `data/`, nommes `{SYMBOL}_{INTERVAL}_{START}_{END}.parquet`. Le cache est deterministe : meme requete = meme fichier.

**Limites yfinance** :

| Intervalle | Historique max |
|-----------|----------------|
| 1m | 7 jours |
| 5m, 15m | 60 jours |
| 1h | 730 jours |
| 1d, 1w | Illimite |

### 3.2 `src/backtesting/engine.py` -- Moteur de backtest

**Responsabilite** : executer des backtests VectorBT et produire des resultats structures + visualisations.

**Classes** :

- `BacktestConfig` : configuration (symbol, interval, dates, cash initial, frais).
- `BacktestResult` : resultat complet (portfolio VectorBT, prix, signaux, metadata actif).
- `ComparisonCurve` : courbe supplementaire a superposer sur le graphique de portefeuille.

**Fonctions cles** :

- `run_backtest(config, entries, exits, price?)` : execute un backtest a partir de signaux booleens pre-calcules.
- `build_plot(result, comparisons?, strategy_name?)` : genere un graphique Plotly a 2 panneaux :
  - Haut : prix + marqueurs achat/vente
  - Bas : valeur du portefeuille vs buy & hold + courbes de comparaison
- `save_plot(fig, path)` : serialise les timestamps et exporte en PNG.
- `print_results(result)` : affiche les metriques cles en console.

### 3.3 `src/evaluation/regime.py` -- Detection de regime

**Responsabilite** : classifier chaque point temporel en regime TRENDING, REVERTING ou UNCERTAIN.

**Indicateurs calcules** :

- **ADX (Average Directional Index)** : mesure la force de la tendance (0-100). Implementaton custom basee sur le True Range et les Directional Movements, lissage Wilder EMA.
- **Exposant de Hurst** : mesure la persistance des prix sur une fenetre glissante. Methode : scaling de la variance des differences lagguees (`Var(X(t+lag) - X(t)) ~ lag^(2H)`). Plus robuste que la methode R/S classique.

**Classification** :

```
TRENDING  : ADX > 25 ET Hurst > 0.40
REVERTING : ADX < 20 ET Hurst < 0.35
UNCERTAIN : tout le reste
```

**Parametres** : `adx_window=14`, `hurst_window=60` (configurables).

### 3.4 `src/agent/grammar.py` -- Grammaire GP

**Responsabilite** : definir les briques elementaires que DEAP combine en arbres de strategie.

**Contexte** : un dictionnaire global `_ctx` contient les Series OHLCV. Il est mis a jour via `set_context(df)` avant chaque evaluation.

**Primitives disponibles** :

| Type | Nom | Signature | Description |
|------|-----|-----------|-------------|
| Prix | Close, High, Low | `() -> SeriesFloat` | Donnees de prix brutes |
| Seuil | T20, T30, T50, T70... | `() -> SeriesFloat` | Constantes en Series |
| Indicateur | SMA7..SMA50 | `(SF) -> SF` | Moyenne mobile (6 fenetres) |
| Indicateur | RSI7..RSI50 | `(SF) -> SF` | RSI (6 fenetres) |
| Indicateur | BBU7..BBU50 | `(SF) -> SF` | Bollinger Band haute |
| Indicateur | BBL7..BBL50 | `(SF) -> SF` | Bollinger Band basse |
| Indicateur | ATR7..ATR50 | `() -> SF` | Average True Range |
| Comparaison | GT, LT | `(SF, SF) -> SB` | Plus grand / plus petit |
| Crossover | XAbove, XBelow | `(SF, SF) -> SB` | Croisement haussier/baissier |
| Logique | AND, OR, NOT | `(SB, SB) -> SB` | Operateurs booleens |
| Booleen | TRUE, FALSE | `() -> SB` | Series constantes |

`SF` = SeriesFloat, `SB` = SeriesBool.

**Wrapper `_safe`** : chaque primitive est enveloppee pour capturer les erreurs (divisions par zero, NaN) et retourner une serie par defaut. Permet a l'evolution de continuer meme avec des arbres invalides.

**Wrapper `_resolve`** : convertit les valeurs sentinelles (`"__close__"`, `"__false__"`) en Series reelles. Necessaire car DEAP stocke les terminaux comme des valeurs statiques.

### 3.5 `src/agent/fitness.py` -- Fonction fitness

**Responsabilite** : evaluer un arbre GP en le transformant en strategie de trading et en mesurant sa performance.

**Pipeline d'evaluation** :

```
Arbre GP
   │ gp.compile()
   ▼
Signal booleen (pd.Series[bool])
   │ rising/falling edges
   ▼
Entries + Exits
   │ vbt.Portfolio.from_signals()
   ▼
Portfolio VectorBT
   │ Sharpe ratio - penalite complexite
   ▼
Score fitness (float)
```

**Filtres de rejet** (retourne -999) :

- Moins de 2 signaux True
- Plus de 80% de signaux True (overtrading)
- Moins de 2 trades executes
- Sharpe NaN ou infini

**Score ajuste** : `score = sharpe - (taille_arbre * penalite_complexite)`

### 3.6 `src/agent/evolution.py` -- Boucle evolutive

**Responsabilite** : orchestrer l'evolution DEAP (population, selection, crossover, mutation).

**Configuration** :

| Parametre | Valeur par defaut | Role |
|-----------|-------------------|------|
| `pop_size` | 150 | Taille de la population |
| `n_gen` | 25 | Nombre de generations |
| `cx_prob` | 0.7 | Probabilite de crossover |
| `mut_prob` | 0.2 | Probabilite de mutation |
| `max_depth` | 8 | Profondeur max des arbres (bloat control) |
| `tournsize` | 5 | Taille du tournoi de selection |

**Operateurs genetiques** :

- **Selection** : tournoi de taille 5 (pression selective moderee)
- **Crossover** : echange de sous-arbres a un point (`cxOnePoint`)
- **Mutation** : remplacement d'un sous-arbre par un nouveau aleatoire (`mutUniform`)
- **Controle du bloat** : les arbres depassant `max_depth` sont rejetes apres crossover/mutation

**Statistiques par generation** : moyenne des fitness viables, meilleur score, nombre d'individus viables (score > -900).

**Validation** : `validate_top_strategies()` decode les top N du Hall of Fame et les evalue sur les sets train ET test pour detecter l'overfit.

---

## 4. Exemples implementes

### Ex1 : `first_backtest.py` -- MA Crossover

Croisement de moyennes mobiles sur un actif configurable.

- **Config** : SYMBOL, INTERVAL, START, END, FAST_MA, SLOW_MA
- **Signaux** : achat quand MA rapide > MA lente, vente quand MA rapide < MA lente
- **Sortie** : metriques console + graphique 2 panneaux (prix+signaux, portefeuille vs buy&hold)

### Ex2 : `parameter_sweep.py` -- Sweep vectorise

Balaye toutes les combinaisons de fenetres MA (fast x slow) en un seul appel vectorise.

- **Grid** : fast=5-50 (pas 5) x slow=20-200 (pas 10) = 190 combinaisons
- **Sortie** : heatmap Sharpe ratio + backtest du meilleur combo

### Ex3 : `walk_forward_optimizer.py` -- Walk-forward RSI+BB

Optimisation walk-forward avec strategie RSI + Bollinger Bands + Stop-Loss/Take-Profit.

- **Fenetre** : 6 mois train, 2 mois test, avance de 2 mois
- **Grid** : RSI (3 periodes x 3 seuils) x BB (3 periodes x 3 alphas) x SL (2) x TP (2) = 324 combos
- **Score** : composite (40% Sharpe + 30% Sortino + 30% Profit Factor)
- **Sortie** : log par fenetre + metriques OOS + comparaison avec Ex1 et Ex2

### Ex4 : `adaptive_strategy.py` -- Strategie adaptive

Bascule automatiquement entre trend-following et mean-reversion selon le regime detecte.

- **Regime** : ADX(14) + Hurst(60) calcules sur les OHLC
- **Trending** : MA(20/50) crossover
- **Reverting** : RSI(14, 30/70) + BB(20, 2.0)
- **Uncertain** : cash (exit force)
- **Sortie** : graphique 3 panneaux (prix+signaux, regime ADX/Hurst, portefeuille 4 strategies)

### Ex5 : `gp_strategy_evolution.py` -- Evolution DEAP

Programmation genetique pour decouvrir des strategies de trading.

- **Population** : 150 individus, 25 generations
- **Grammaire** : ~50 primitives (indicateurs, comparaisons, logique)
- **Fitness** : Sharpe VectorBT - penalite complexite
- **Validation** : train 2020-2024 / test 2025-2026
- **Sortie** : top 5 strategies avec detection d'overfit + graphique OOS

---

## 5. Resultats et enseignements

### 5.1 BTC-USD (2020-2026, daily)

| Strategie | Rendement | Sharpe | Max DD | Trades |
|-----------|-----------|--------|--------|--------|
| Buy & Hold | ~+1200% | -- | -77% | 0 |
| Ex1: MA(10/50) | ~+800% | -- | -- | ~80 |
| Ex2: MA(40/200) best | ~+500% | -- | -- | ~20 |
| Ex3: WF RSI+BB | -35% | -0.00 | -77% | 13 |
| **Ex4: Adaptive** | **+257%** | **0.92** | **-23%** | **23** |
| Ex5: GP best (train) | +1458% | 1.41 | -41% | 48 |
| Ex5: GP best (test) | -41% | -1.24 | -49% | 14 |

### 5.2 Enseignements cles

1. **Le type de strategie doit matcher le regime de marche.** BTC en bull run favorise le trend-following. Appliquer du mean-reversion sur un marche en tendance est destructeur.

2. **La strategie adaptive est le meilleur compromis risque/rendement.** +257% avec seulement -23% de drawdown, vs -77% pour le buy & hold. Elle ne bat pas le buy & hold en rendement pur, mais le drawdown est 3x plus faible.

3. **L'evolution GP decouvre des patterns mais overfitte.** +1458% en train, -41% en test. Les garde-fous (walk-forward dans la fitness, diversite forcee) sont indispensables.

4. **La grammaire GP converge vers un motif unique.** Les 5 meilleures strategies sont toutes des variantes de `GT(ATR, SMA(ATR))` (expansion de volatilite). Besoin de niching/speciation pour explorer d'autres families.

---

## 6. Feuille de route

### Etape 1 : Renforcer les garde-fous GP

- Walk-forward integre dans la fitness (pas juste sur le train complet)
- Niching/speciation pour forcer la diversite des strategies
- Augmenter la population (300+) et les generations (50+)

### Etape 2 : Optuna + VectorBT

- Optimisation bayesienne des hyperparametres du GP (taille pop, profondeur, taux mutation)
- Exploration structuree de templates de strategies via `suggest_categorical()`

### Etape 3 : PySR (Regression symbolique)

- Decouverte de nouveaux indicateurs/facteurs alpha a partir des donnees brutes
- Injection des indicateurs decouverts dans la grammaire GP

### Etape 4 : LLM Orchestrateur (Claude)

- Analyser les resultats des backtests et proposer des hypotheses
- Orienter la recherche GP (modifier la grammaire, ajuster les seuils)
- Generer des rapports d'analyse automatiques

### Etape 5 : Paper Trading IB

- Connexion a Interactive Brokers via ib_insync
- Deploiement des meilleures strategies en paper trading
- Monitoring et alertes automatiques

### Etape 6 : Trading reel

- Passage progressif du paper au reel avec limites de position
- Circuit breakers et gestion du risque en temps reel
