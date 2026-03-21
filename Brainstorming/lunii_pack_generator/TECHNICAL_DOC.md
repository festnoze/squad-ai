# Lunii Pack Generator — Documentation Technique

> Generateur automatique de packs STUdio pour la Fabrique a Histoires Lunii

---

## 1. Vue d'ensemble

**lunii-pack-generator** est un outil CLI Python qui genere un pack `.zip` importable dans [STUdio](https://github.com/jersou/studio-pack-generator) a partir d'une arborescence locale de fichiers MP3.

### Probleme resolu

Creer manuellement un pack de 45 histoires reparties en plusieurs categories via l'interface graphique de STUdio est prohibitif. Cet outil automatise l'integralite du processus :

1. **Normalisation** des noms de dossiers (ajout de prefixes numeriques)
2. **Validation** de l'arborescence source
3. **Generation** du pack via `studio-pack-generator` (Deno/TypeScript)
4. **Recuperation** du `.zip` final pret a etre importe dans STUdio

### Stack technique

| Composant | Technologie |
|-----------|-------------|
| CLI & logique metier | Python >= 3.11 |
| Interface terminal | Click + Rich |
| Gestion de paquets | uv |
| Generation du pack | studio-pack-generator (Deno/TypeScript) |
| Conversion audio | FFmpeg |
| Generation d'images | ImageMagick |
| TTS menus | picoTTS (Linux) / Windows TTS natif |

---

## 2. Architecture du projet

```
lunii_pack_generator/
├── pyproject.toml                 # Metadonnees projet, deps, entry point
├── .gitignore
├── TECHNICAL_DOC.md               # Ce document
├── bin/                           # Sources studio-pack-generator (Deno)
│   ├── studio_pack_generator.ts   # Point d'entree Deno (requis)
│   ├── deno.json                  # Config Deno (v0.5.14)
│   ├── gen_pack.ts                # Logique de generation de pack
│   ├── types.ts                   # Types TypeScript
│   ├── utils/                     # Utilitaires (audio, images, etc.)
│   ├── generate/                  # Modules de generation (TTS, images)
│   ├── serialize/                 # Serialisation du pack
│   └── vendor/                    # Deps vendorisees Deno
├── source/                        # Dossier source MP3 (gitignore)
├── output/                        # .zip genere (gitignore)
├── lunii_pack_generator/          # Package Python principal
│   ├── __init__.py                # Version (0.1.0)
│   ├── cli.py                     # Point d'entree Click
│   ├── normalizer.py              # Renommage automatique des dossiers
│   ├── validator.py               # Validation de l'arborescence
│   ├── generator.py               # Orchestration subprocess Deno
│   └── utils.py                   # Helpers (detection, formatage)
└── tests/
    ├── test_normalizer.py         # 7 tests
    ├── test_validator.py          # 12 tests
    ├── test_generator.py          # 11 tests
    └── test_utils.py              # 12 tests
```

### Diagramme de dependances entre modules

```
cli.py
 ├── normalizer.py
 ├── validator.py
 ├── generator.py
 │    └── utils.py (detect_deno, detect_spg_source, format_size)
 └── utils.py (detect_deno, detect_spg_source, format_size)
```

---

## 3. Prerequis systeme

### 3.1 Python & uv

```bash
# Python >= 3.11 requis
python --version

# Installer uv (gestionnaire de paquets)
# Windows :
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# Linux/macOS :
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.2 Deno

Le generateur de pack est ecrit en TypeScript et necessite Deno :

```bash
# Windows :
irm https://deno.land/install.ps1 | iex
# Linux/macOS :
curl -fsSL https://deno.land/install.sh | sh

deno --version   # verifier l'installation
```

> **Note** : Les binaires precompiles de studio-pack-generator (Deno 2.1.x) ont un bug BigInt sur Windows. Utiliser Deno >= 2.2 avec les sources TypeScript evite ce probleme.

### 3.3 Outils de conversion

| Outil | Role | Installation |
|-------|------|-------------|
| FFmpeg | Conversion audio, extraction d'images | `apt install ffmpeg` / `brew install ffmpeg` / [ffmpeg.org](https://ffmpeg.org/download.html) |
| ImageMagick | Generation des images de menus | `apt install imagemagick` / `brew install imagemagick` / [imagemagick.org](https://imagemagick.org/script/download.php) |
| picoTTS | TTS pour titres audio des menus (Linux) | `apt install libttspico-utils` |

Sur Windows, le TTS natif est utilise automatiquement a la place de picoTTS.

### 3.4 Verification

```bash
lunii-gen --check-deps
```

Affiche l'etat de chaque dependance :
```
  ✓ deno → C:\Users\...\deno.exe
  ✓ studio-pack-generator (sources) → bin\studio_pack_generator.ts
  ✓ ffmpeg → C:\...\ffmpeg.exe
  ✗ convert (ImageMagick) — introuvable
```

---

## 4. Installation du projet

```bash
cd lunii_pack_generator
uv venv                    # Cree .venv/
uv sync                    # Installe toutes les deps + entry point lunii-gen

# Activer le venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # Linux/macOS

# Verifier
lunii-gen --help
```

---

## 5. Reference des modules

### 5.1 `utils.py` — Helpers

#### Constantes

```python
SPG_ENTRY_POINT = "studio_pack_generator.ts"
```

#### `detect_deno() -> Path | None`

Cherche le binaire `deno` dans le PATH systeme via `shutil.which()`.

#### `detect_spg_source(bin_dir: Path | None = None) -> Path | None`

Localise `studio_pack_generator.ts` dans l'ordre :
1. `{bin_dir}/studio_pack_generator.ts` (si fourni)
2. `./bin/studio_pack_generator.ts`

#### `format_size(size_bytes: int) -> str`

Formate une taille en octets en chaine lisible :

| Entree | Sortie |
|--------|--------|
| 500 | `"500 o"` |
| 1 536 | `"1.5 Ko"` |
| 5 242 880 | `"5.0 Mo"` |
| 2 147 483 648 | `"2.00 Go"` |

---

### 5.2 `normalizer.py` — Renommage automatique

#### Structures de donnees

```python
@dataclass
class RenameAction:
    old_path: Path    # Chemin original
    new_path: Path    # Chemin apres renommage
    old_name: str     # Nom original du dossier
    new_name: str     # Nouveau nom avec prefixe
```

#### `normalize_source(source_dir: Path) -> list[RenameAction]`

Point d'entree principal. Parcourt recursivement l'arborescence et renomme les dossiers sans prefixe numerique.

**Pattern de detection** : `^\d+\s*-\s*` (ex: `01 - `, `1-`, `001 - `)

**Algorithme** :
1. A chaque niveau, trier les dossiers par nom
2. Pour chaque dossier sans prefixe, attribuer un numero base sur sa position
3. Format : `"{numero zero-padde} - {nom original}"`
4. Largeur minimum : 2 chiffres (01, 02, ... 99)
5. Descendre recursivement dans les sous-dossiers renommes

**Exemple** :
```
Avant :                          Apres :
source/                          source/
├── Aventures/                   ├── 01 - Aventures/
│   ├── Foret/                   │   ├── 01 - Foret/
│   └── Mer/                     │   └── 02 - Mer/
└── Contes/                      └── 02 - Contes/
```

> **Attention** : Le renommage modifie physiquement les dossiers sur disque via `Path.rename()`.

---

### 5.3 `validator.py` — Validation recursive

#### Structures de donnees

```python
@dataclass
class CategoryInfo:
    name: str                                  # Nom du dossier
    path: Path                                 # Chemin complet
    mp3_files: list[Path]                      # Fichiers MP3 a ce niveau
    subcategories: list[CategoryInfo]           # Sous-categories imbriquees

    @property
    def total_stories(self) -> int:            # Comptage recursif des MP3
        ...

@dataclass
class ValidationReport:
    valid: bool                                # Validation globale OK/KO
    categories: list[CategoryInfo]             # Categories de premier niveau
    total_stories: int                         # Nombre total de MP3
    warnings: list[str]                        # Avertissements non bloquants
    errors: list[str]                          # Erreurs bloquantes
```

#### `validate_source(source_dir: Path) -> ValidationReport`

Valide recursivement l'arborescence source.

**Regles de validation** :

| Regle | Severite | Description |
|-------|----------|-------------|
| Dossier source existe | Erreur | Le chemin doit exister et etre un dossier |
| Au moins 1 sous-dossier | Erreur | Doit contenir des categories |
| MP3 non vide | Erreur | Taille > 0 octets obligatoire |
| Dossier sans MP3 ni sous-dossier | Warning | Ignore avec avertissement |

**Recursivite** : Chaque dossier est explore en profondeur. Un dossier peut contenir a la fois des fichiers MP3 et des sous-dossiers — les deux sont pris en compte.

---

### 5.4 `generator.py` — Execution de studio-pack-generator

#### `GeneratorError(Exception)`

Exception personnalisee levee en cas d'echec de la generation.

#### `build_command(deno_path, spg_entry, source_dir, *, lang, delay, auto_next) -> list[str]`

Construit la commande `deno run` :

```
deno run -A /chemin/absolu/studio_pack_generator.ts \
  --lang fr \
  --add-delay \
  --auto-next-story-transition \
  /chemin/vers/source
```

| Parametre | Flag CLI genere |
|-----------|-----------------|
| `lang="fr"` | `--lang fr` |
| `delay=True` | `--add-delay` |
| `auto_next=True` | `--auto-next-story-transition` |

#### `find_generated_zip(source_dir: Path) -> Path | None`

Cherche le `.zip` produit par studio-pack-generator :
1. Dans le dossier parent du source (nom contenant le nom du source ou "pack")
2. Le `.zip` le plus recent dans le parent
3. Recursivement dans le dossier source

#### `run_generation(source_dir, output_dir, bin_dir, *, lang, delay, auto_next) -> Path`

Orchestration complete de la generation :

```
detect_deno()          → Erreur si absent
detect_spg_source()    → Erreur si absent
build_command()        → Construire la commande
subprocess.run()       → Executer (cwd = source_dir.parent, encoding UTF-8)
find_generated_zip()   → Localiser le .zip
shutil.move()          → Deplacer dans output_dir
```

**Parametres subprocess** :
- `cwd` : dossier parent du source (requis par studio-pack-generator)
- `encoding="utf-8"` : evite les erreurs cp1252 sur Windows
- `errors="replace"` : remplace les octets invalides par `�`

---

### 5.5 `cli.py` — Interface Click

#### Options CLI

```
Usage: lunii-gen [OPTIONS]

Options:
  --source PATH           Dossier source MP3           [default: ./source]
  --output PATH           Dossier sortie .zip          [default: ./output]
  --bin PATH              Dossier sources SPG           [default: ./bin/]
  --lang TEXT             Langue TTS                    [default: fr]
  --delay / --no-delay    Silence 1s debut/fin          [default: delay]
  --auto-next / --no-auto-next  Enchainement auto      [default: auto-next]
  --check-deps            Verifier les deps et quitter
  --help                  Afficher l'aide
```

#### Affichage Rich

L'outil utilise Rich pour un affichage structure :

- **Panel** bleu : titre du programme
- **Panel** jaune : renommages effectues
- **Tree** : arborescence des categories avec comptage MP3 et tailles
- **Icones** : `✓` (OK), `✗` (erreur), `⚠` (warning)
- **Rule** : separateur pour la sortie studio-pack-generator

---

## 6. Flux d'execution complet

```
lunii-gen --source ./source --output ./output --lang fr
│
├─ 1. Affichage du panneau de bienvenue
│
├─ 2. Verification que le dossier source existe
│
├─ 3. NORMALISATION (normalizer.py)
│     ├─ Parcours recursif de l'arborescence
│     ├─ Detection des dossiers sans prefixe numerique
│     ├─ Renommage : "Tome 1" → "01 - Tome 1"
│     └─ Affichage des renommages effectues
│
├─ 4. VALIDATION (validator.py)
│     ├─ Verification recursive de la structure
│     ├─ Collecte des MP3 et sous-categories
│     ├─ Detection des erreurs (MP3 vides, dossiers absents)
│     └─ Detection des warnings (dossiers vides)
│
├─ 5. AFFICHAGE
│     ├─ Si erreurs → afficher et exit(1)
│     ├─ Arbre Rich des categories/histoires
│     └─ Warnings eventuels
│
├─ 6. CONFIRMATION utilisateur
│     └─ "Lancer la generation ?" [O/n]
│
├─ 7. GENERATION (generator.py)
│     ├─ Detection de deno dans le PATH
│     ├─ Detection de studio_pack_generator.ts dans bin/
│     ├─ Construction de la commande deno run
│     ├─ Execution subprocess
│     │   └─ deno run -A studio_pack_generator.ts [options] source/
│     │       ├─ FFmpeg : conversion/validation audio
│     │       ├─ ImageMagick : generation images menus (320x240)
│     │       ├─ TTS : generation audio des titres de menus
│     │       └─ ZIP : creation du pack .zip STUdio
│     ├─ Recherche du .zip genere
│     └─ Deplacement vers output/
│
└─ 8. RESULTAT
      ├─ Affichage du chemin et taille du .zip
      └─ "Importez {pack}.zip dans STUdio via 'Open from file'."
```

---

## 7. Gestion des images

studio-pack-generator gere automatiquement les images de navigation :

### Auto-generation (comportement par defaut)

Si aucune image n'est fournie, ImageMagick genere des images textuelles avec le nom du dossier/fichier. Format : **320x240 pixels**.

### Images personnalisees

Des images peuvent etre placees manuellement dans l'arborescence :

| Fichier | Role |
|---------|------|
| `title.png` | Image du pack (menu racine) |
| `0-item.png` | Image d'une categorie/sous-menu |
| `{nom}.item.png` | Vignette d'une histoire (ex: `01.item.png` pour `01.mp3`) |

Formats acceptes : PNG, JPG, BMP. Les images sont automatiquement redimensionnees en 320x240.

### Exemple

```
source/
├── title.png                    ← image du pack
├── 01 - Aventures/
│   ├── 0-item.png               ← image du menu "Aventures"
│   ├── 01.mp3
│   ├── 01.item.png              ← vignette histoire 01
│   ├── 02.mp3
│   └── 02.item.png              ← vignette histoire 02
└── 02 - Contes/
    ├── 0-item.png
    ├── 01.mp3                   ← pas de .item.png → auto-generee
    └── 02.mp3
```

---

## 8. Options de studio-pack-generator

Les options transmises par `generator.py` a `deno run` :

| Option | Description | Active par defaut |
|--------|-------------|:-----------------:|
| `--lang fr` | Langue TTS pour les menus | Oui |
| `--add-delay` | 1 seconde de silence debut/fin | Oui |
| `--auto-next-story-transition` | Enchainement automatique | Oui |

Options supplementaires disponibles dans studio-pack-generator (non exposees dans la CLI Python) :

| Option | Description |
|--------|-------------|
| `--night-mode` | Transitions mode nuit |
| `--skip-audio-convert` | Ne pas convertir l'audio |
| `--skip-image-convert` | Ne pas convertir les images |
| `--skip-audio-item-gen` | Ne pas generer les items audio |
| `--skip-image-item-gen` | Ne pas generer les images |
| `--skip-extract-image-from-mp3` | Ne pas extraire les images des MP3 |
| `--image-item-gen-font` | Police pour les images generees (defaut: Arial) |
| `--output-folder` | Dossier de sortie du ZIP |
| `--seek-story` | Couper le debut (HH:mm:ss ou N sec) |

---

## 9. Gestion des erreurs

### Erreurs bloquantes (exit code 1)

| Situation | Source | Message |
|-----------|--------|---------|
| Dossier source inexistant | validator | "Le dossier source n'existe pas" |
| Source n'est pas un dossier | validator | "Le chemin source n'est pas un dossier" |
| Aucune categorie | validator | "Aucune categorie ni fichier .mp3 trouve" |
| MP3 vide (0 octets) | validator | "Le fichier MP3 est vide (0 octets)" |
| Deno introuvable | generator | "Deno introuvable dans le PATH" |
| Sources SPG introuvables | generator | "Sources studio-pack-generator introuvables" |
| Subprocess echoue | generator | "studio-pack-generator a echoue (code retour: X)" |
| ZIP introuvable apres generation | generator | "Aucun fichier .zip n'a ete trouve" |

### Warnings non bloquants

| Situation | Message |
|-----------|---------|
| Dossier sans MP3 ni sous-dossier | "ne contient aucun fichier .mp3 ni sous-dossier utile — ignore" |

### Encodage Windows

Le subprocess utilise `encoding="utf-8"` et `errors="replace"` pour eviter les `UnicodeDecodeError` lies a cp1252 sur Windows.

---

## 10. Tests

### Execution

```bash
cd lunii_pack_generator
uv run pytest -v
```

### Couverture des tests (42 tests)

#### `test_utils.py` (12 tests)

| Test | Description |
|------|-------------|
| `TestDetectDeno::test_found_in_path` | Deno present dans le PATH |
| `TestDetectDeno::test_not_found` | Deno absent |
| `TestDetectSpgSource::test_found_in_custom_dir` | SPG dans dossier custom |
| `TestDetectSpgSource::test_found_in_default_bin` | SPG dans ./bin/ |
| `TestDetectSpgSource::test_not_found` | SPG introuvable |
| `TestFormatSize::test_bytes` | 500 → "500 o" |
| `TestFormatSize::test_kilobytes` | 1536 → "1.5 Ko" |
| `TestFormatSize::test_megabytes` | 5 Mo |
| `TestFormatSize::test_gigabytes` | 2 Go |
| `TestFormatSize::test_zero` | 0 → "0 o" |
| `TestFormatSize::test_exact_1kb` | 1024 → "1.0 Ko" |
| `TestFormatSize::test_exact_1mb` | 1 Mo |

#### `test_normalizer.py` (7 tests)

| Test | Description |
|------|-------------|
| `TestNormalizeSimple::test_adds_prefix_to_all` | 3 dossiers → 01, 02, 03 |
| `TestNormalizeSimple::test_skips_already_prefixed` | Garde les prefixes existants |
| `TestNormalizeSimple::test_no_rename_needed` | Rien a renommer |
| `TestNormalizeRecursive::test_renames_nested_dirs` | Renommage recursif (5 actions) |
| `TestNormalizeRecursive::test_mixed_nested_levels` | Mix prefixe/non-prefixe |
| `TestNormalizeEdgeCases::test_empty_source` | Dossier vide |
| `TestNormalizeEdgeCases::test_only_files_no_dirs` | Pas de sous-dossiers |

#### `test_validator.py` (12 tests)

| Test | Description |
|------|-------------|
| `TestNominal::test_valid_flat_tree` | 2 categories, 5 MP3 |
| `TestNominal::test_single_category` | 1 categorie, 1 MP3 |
| `TestNominal::test_nested_structure` | Tomes → Chapitres (5 MP3) |
| `TestNominal::test_deep_nesting` | 3 niveaux de profondeur |
| `TestErrors::test_source_does_not_exist` | Chemin inexistant |
| `TestErrors::test_source_is_a_file` | Fichier au lieu de dossier |
| `TestErrors::test_empty_source_no_categories` | Dossier vide |
| `TestErrors::test_category_without_mp3_is_skipped` | Categorie sans MP3 → warning |
| `TestErrors::test_all_categories_empty` | Toutes vides → 0 stories |
| `TestErrors::test_empty_mp3_file` | MP3 0 octets → erreur |
| `TestNested::test_nested_empty_subdir_skipped` | Sous-dossier vide ignore |
| `TestNested::test_mixed_mp3_and_subdirs` | MP3 + sous-dossiers dans meme niveau |

#### `test_generator.py` (11 tests)

| Test | Description |
|------|-------------|
| `TestBuildCommand::test_default_options` | Commande avec options par defaut |
| `TestBuildCommand::test_no_delay` | Sans `--add-delay` |
| `TestBuildCommand::test_no_auto_next` | Sans `--auto-next-story-transition` |
| `TestBuildCommand::test_custom_lang` | `--lang en` |
| `TestFindGeneratedZip::test_zip_in_parent` | ZIP dans dossier parent |
| `TestFindGeneratedZip::test_zip_in_source` | ZIP dans dossier source |
| `TestFindGeneratedZip::test_no_zip_found` | Aucun ZIP |
| `TestRunGeneration::test_deno_not_found_raises` | Deno absent → GeneratorError |
| `TestRunGeneration::test_spg_source_not_found_raises` | SPG absent → GeneratorError |
| `TestRunGeneration::test_subprocess_failure_raises` | Code retour != 0 → GeneratorError |
| `TestRunGeneration::test_successful_generation` | Flow complet mock → ZIP dans output |

### Strategie de mock

- `subprocess.run` → mock pour eviter d'executer Deno
- `detect_deno()` / `detect_spg_source()` → mock pour controler les chemins
- `shutil.which()` → mock pour simuler la presence/absence des outils
- `monkeypatch.chdir()` → isoler les tests du filesystem reel
- `tmp_path` (pytest) → dossiers temporaires pour chaque test

---

## 11. Utilisation

### Commande de base

```bash
lunii-gen --source ./source
```

### Toutes les options

```bash
lunii-gen \
  --source ./mes_histoires \
  --output ./dist \
  --bin ./mon_dossier_spg \
  --lang fr \
  --delay \
  --auto-next
```

### Apres generation

1. Ouvrir **STUdio** (v0.4.2+)
2. Menu → **"Open from file"** → selectionner le `.zip`
3. Connecter la **Lunii** via USB
4. Transferer le pack depuis STUdio vers la Lunii

---

## 12. Structure attendue du dossier source

### Avant normalisation

```
source/
├── Aventures/
│   ├── 01.mp3
│   ├── 02.mp3
│   └── 03.mp3
├── Contes/
│   ├── La belle histoire.mp3
│   └── Le petit chat.mp3
└── Tome 4/                     ← vide, sera ignore
```

### Apres normalisation + validation

```
source/
├── 01 - Aventures/              ← prefixe ajoute
│   ├── 01.mp3                   ✓
│   ├── 02.mp3                   ✓
│   └── 03.mp3                   ✓
├── 02 - Contes/                 ← prefixe ajoute
│   ├── La belle histoire.mp3    ✓
│   └── Le petit chat.mp3       ✓
└── 03 - Tome 4/                ← prefixe ajoute, mais ignore (vide)
     ⚠ "ne contient aucun fichier .mp3 — ignore"
```

### Structure imbriquee (supportee)

```
source/
├── Tome 1/
│   ├── Chapitre 1/
│   │   ├── 01.mp3
│   │   └── 02.mp3
│   └── Chapitre 2/
│       └── 01.mp3
└── Tome 2/
    ├── 01.mp3               ← MP3 + sous-dossiers dans le meme niveau
    └── Bonus/
        └── 01.mp3
```

→ Normalise en :

```
source/
├── 01 - Tome 1/
│   ├── 01 - Chapitre 1/
│   │   ├── 01.mp3
│   │   └── 02.mp3
│   └── 02 - Chapitre 2/
│       └── 01.mp3
└── 02 - Tome 2/
    ├── 01.mp3
    └── 01 - Bonus/
        └── 01.mp3
```

---

## 13. Hors scope

- Conversion audio (MP3 uniquement, deja au bon format)
- Generation des images d'illustration (deleguee a ImageMagick via studio-pack-generator)
- Transfert USB vers la Lunii (fait manuellement depuis STUdio)
- Support RSS ou podcast
- Interface graphique
