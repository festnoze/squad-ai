# Benchmark langage cible — Python / Go / Rust (Niveau A : mesuré)

Décider le langage de l'app **générée par Autospec** sur des mesures, pas sur de
l'opinion. Critère = adéquation à une **boucle de génération autonome rouge→vert**,
pas « meilleur langage dans l'absolu ».

- **Machine** : Windows 10, 20 cœurs logiques. Toolchains : Python 3.14.5,
  Go 1.26.3, Rust 1.91.1 / Cargo 1.91.1. Builds **debug** (= ce qu'exercerait la boucle de tests).
- **Spec identique** dans les 3 langages : lib domaine `TaskBoard` (validation de
  titre/priorité, types d'erreur, exhaustivité de statut, tri par priorité, stats)
  + **9 tests équivalents**. Code : `python/`, `go/`, `rust/`.
- Reproductible : voir les commandes en bas. Chaque suite est **verte** (9/9).

## 1. Résultats — coût de la boucle (lib domaine, sans dépendance externe)

| Métrique | Python | Go | Rust |
|---|---|---|---|
| Cold compile+test (cache vidé) | ~1,13 s¹ | **15,4 s** | 3,1 s |
| Cold build seul (binaire/lib) | n/a | 9,1 s | **0,77 s** |
| **Warm « édition→test »** (métrique clé) | **1,13 s** | 1,78 s | 1,04 s |
| LOC implémentation (non vides) | **57** | 92² | 86 |
| Tests verts | 9/9 | 9/9 | 9/9 |

¹ Python n'a pas d'étape de compile : c'est le temps pytest (surtout overhead de démarrage).
² Go gonflé d'~15 lignes par un `trimSpace` manuel (j'aurais dû utiliser `strings.TrimSpace`) → ~77 réel.

> **Surprise n°1** : une fois le cache chaud, le coût « édition→test » est **dans
> le même ordre de grandeur pour les trois** (1,0–1,8 s). Le « Rust compile
> lentement » est **faux sans dépendances** : ici Rust (1,04 s) bat Go (1,78 s) à
> chaud. La vitesse de compile n'est PAS le différenciateur qu'on imagine pour
> l'itération.

## 2. Résultats — backend web réaliste (avec dépendances)

C'est ici que l'écart réel apparaît. Go web = `net/http` (stdlib, **0 dép externe**) ;
Rust web = `axum + tokio + serde` (la stack idiomatique).

| Métrique | Go (net/http) | Rust (axum+tokio+serde) |
|---|---|---|
| **Cold build** (1re itération / projet neuf) | 17,8 s | **44,5 s** |
| Dépendances transitives compilées | 0 | **132 crates** |
| Warm build incrémental | **1,26 s** | 1,78 s |

> **Surprise n°2 (le vrai écart)** : le cold build Rust avec deps = **44,5 s et 132
> crates** à compiler, vs **17,8 s et zéro dép externe** pour Go. La stdlib
> « batteries incluses » de Go fait qu'un backend complet ne télécharge/compile
> souvent **rien** → cold build qui reste bon marché. Pour une **usine** qui
> régénère/reconstruit des projets et **ajoute des dépendances**, Rust paie une
> taxe lourde et répétée. À chaud, l'écart se referme (1,26 vs 1,78 s).

## 3. Résultats — garanties compile-time (la thèse « le compilateur = un linter gratuit »)

**Expérience décisive** : on ajoute un 3ᵉ statut `Cancelled` à l'enum
`TaskStatus`, **sans toucher la logique** (`complete`, `pending`, `stats`), et on
regarde qui attrape la régression *avant* d'exécuter le moindre test.

| Langage | Résultat | Quand le bug est attrapé |
|---|---|---|
| **Rust** | ❌ **Refuse de compiler** : `error[E0004]: non-exhaustive patterns: TaskStatus::Cancelled not covered` + suggestion de fix | **Compile-time** (avant tout test) |
| **Go** | ✅ `go build` **et** `go vet` passent | Jamais (exhaustivité = linter tiers `exhaustive`, hors compilateur). Bug silencieux. |
| **Python** | ✅ `import` OK | **Runtime** seulement (si jamais exercé). Bug silencieux. |

Classes d'erreurs attrapées **par le compilateur** (donc déchargées du linter + des tests) :

| Classe d'erreur | Python | Go | Rust |
|---|---|---|---|
| Null / absence (`None`/`nil`) | runtime | runtime (`nil` deref) | **compile** (`Option<T>`) |
| Erreur ignorée | runtime | linter (`errcheck`) | **compile** (`#[must_use]` sur `Result`) |
| `match`/`switch` non exhaustif | jamais | linter tiers | **compile** (`E0004`) |
| Data race | runtime (`-race`) | runtime (`-race`) | **compile** (`Send`/`Sync`) |
| Erreur de type | runtime / mypy | **compile** | **compile** |

> **Surprise n°3 — ta thèse est vérifiée** : Rust déplace à gauche (compile-time)
> 4 classes de bugs que Go renvoie au linter/runtime et que Python ne voit qu'au
> runtime. Dans une boucle autonome à relecture humaine quasi nulle, **« ça
> compile » en Rust = un signal de correction bien plus fort** qu'en Go/Python.

## 4. Lecture pour Autospec — le compromis

```
                débit de boucle  ───────────────►
   Python  ████████████████████  (0 compile, génération la + fiable, 0 garantie)
   Go       ███████████████      (compile rapide, deps stdlib, surface minime → l'IA bloque peu)
   Rust     ████████             (cold build lourd + risque borrow-checker/async → blocages)

                correction par itération  ───────►
   Python  ████                  (tout au runtime)
   Go      ██████████            (typage + erreurs explicites, mais null + non-exhaustif passent)
   Rust    ████████████████████  (null/exhaustivité/erreurs non gérées/races attrapés à la compile)
```

- **Go optimise le DÉBIT** : compile bon marché même en web (stdlib), langage à
  toute petite surface → l'IA produit du code régulier qui compile au 1er/2e
  essai, se « coince » rarement. Idéal pour la fiabilité de **l'usine**.
- **Rust optimise la CORRECTION** : le compilateur fait gratuitement le travail
  du linter + d'une partie des tests (exhaustivité, null, erreurs non gérées,
  races). Au prix d'un cold build lourd (44 s / 132 crates) et d'un **risque de
  non-convergence** (luttes borrow-checker, async `Send`/`Sync`) que la boucle
  doit gérer (cap de tours + heuristiques). Idéal quand la correction du
  **produit** prime sur le débit.
- **Python = référence** : génération la plus fiable (training set massif), mais
  **zéro** garantie compile-time — toute la charge retombe sur les tests + le
  linter, ce qu'on cherche justement à réduire.

## 5. Conclusion (Niveau A)

**Pour la boucle autonome d'Autospec : Go par défaut, Rust en option ciblée.**

1. Une fois à chaud, le coût d'itération est comparable (1–1,8 s) — la vitesse de
   compile **ne tranche pas**.
2. Le vrai écart est au **cold build avec dépendances** (Rust 44 s/132 crates vs
   Go 18 s/0 dép) : pénalisant pour une usine qui reconstruit et ajoute des deps.
   → avantage **Go**.
3. La **petite surface** de Go minimise les blocages de l'IA (pas de borrow
   checker, pas d'async fragmenté). → avantage **Go** pour le débit de boucle.
4. La **richesse compile-time** de Rust décharge réellement linter + tests
   (exhaustivité/null/erreurs/races) → avantage **Rust** pour la correction
   quand la relecture humaine est minimale.

Donc : **Go pour la fiabilité de l'usine, Rust pour la fiabilité du produit
généré.** Greenfield v1 → **Go**. Produit où la sûreté prime (systèmes, latence
sans GC, garanties dures) → **Rust**, avec garde-fous anti-non-convergence.

> ⚠️ Limite de ce niveau : il mesure les **toolchains**, pas le **taux de réussite
> du modèle**. Le facteur décisif restant — « le modèle atteint-il le vert, en
> combien d'itérations, en se coinçant combien de fois, par langage et par
> modèle (Opus / GPT-5.x codex / Gemini 3.x) » — se mesure au **Niveau B** en
> branchant la pipeline Autospec sur des cibles Go/Rust (cf. BACKLOG L1).

## Reproduire

```powershell
# Lib domaine
cd python; python -m venv .venv; .\.venv\Scripts\python -m pip install pytest; .\.venv\Scripts\python -m pytest -q
cd ..\go;   go clean -cache; go test -count=1 ./...        # cold ; relancer pour warm
cd ..\rust; cargo clean;     cargo test                    # cold ; relancer pour warm

# Cold build web (avec deps)
cd ..\go-web;   go clean -cache; go build
cd ..\rust-web; cargo clean;     cargo build

# Expérience exhaustivité : ajouter `Cancelled` à l'enum TaskStatus dans chaque
# langage SANS toucher la logique, puis : cargo build (échoue) ; go build+vet (passe) ; python -c import (passe).
```
