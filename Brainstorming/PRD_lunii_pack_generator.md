# PRD — Lunii Pack Generator
> Document de référence pour Claude Code

---

## 1. Contexte et objectif

Générer automatiquement un pack d'histoires pour la **Fabrique à Histoires Lunii** à partir d'une arborescence locale de fichiers MP3, sans passer par l'interface graphique de STUdio.

**Problème résolu :** 45 histoires réparties en 3 catégories → créer la navigation à la main dans STUdio est prohibitif. Le script prend l'arborescence source, valide les fichiers, puis délègue la génération du pack à `studio-pack-generator`.

**Sortie attendue :** un fichier `.zip` importable directement dans STUdio 0.4.2 via *"Open from file"*, puis transférable sur la Lunii.

---

## 2. Structure de l'arborescence source

```
source/
├── 01 - Catégorie A/
│   ├── 01.mp3
│   ├── 02.mp3
│   └── ...   ← 15 fichiers
├── 02 - Catégorie B/
│   └── ...   ← 15 fichiers
└── 03 - Catégorie C/
    └── ...   ← 15 fichiers
```

**Règles :**
- Les dossiers de catégories **doivent** être préfixés (`01 - `, `02 - `) pour garantir l'ordre dans le menu racine.
- Les fichiers MP3 sont nommés `01.mp3`, `02.mp3`, etc. → ordre alphanumérique suffit.
- Format audio : **MP3 uniquement**, 1 fichier = 1 histoire.
- Pas d'images fournies → les images de menus sont **générées automatiquement** par ImageMagick.

---

## 3. Setup du projet Python

### 3.1 Prérequis système

```
Python >= 3.11
uv (gestionnaire de paquets et venv)
```

Installer `uv` si absent :
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# ou sur Windows :
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3.2 Initialisation du projet

```bash
uv init lunii-pack-generator
cd lunii-pack-generator
uv venv                    # crée .venv/
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 3.3 Dépendances Python

```bash
uv add click rich pathlib
uv add --dev pytest
```

**`pyproject.toml` attendu :**

```toml
[project]
name = "lunii-pack-generator"
version = "0.1.0"
description = "Générateur automatique de packs Lunii depuis une arborescence MP3"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0",      # CLI arguments
    "rich>=13.0",      # output console coloré
]

[project.scripts]
lunii-gen = "lunii_pack_generator.cli:main"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
]
```

---

## 4. Outils système à installer (hors Python)

Ces outils sont appelés en sous-processus par `studio-pack-generator`. Ils doivent être disponibles dans le `PATH`.

### Linux / WSL (recommandé)

```bash
sudo apt update && sudo apt install -y \
    ffmpeg \              # conversion audio + extraction images
    libttspico-utils \    # TTS picoTTS pour générer les titres audio des menus
    imagemagick           # génération des images de menus
```

### macOS

```bash
brew install ffmpeg imagemagick
# picoTTS n'est pas dispo via brew → utiliser l'option --skip-audio-item-gen
# ou passer par une VM Linux / Docker
```

### Windows

Utiliser le **binaire Windows** de `studio-pack-generator` qui embarque ffmpeg et imagemagick.
Le TTS Windows natif est utilisé à la place de picoTTS.

---

## 5. Installation de `studio-pack-generator`

`studio-pack-generator` est un outil externe (TypeScript/Deno) qui fait la vraie génération du pack STUdio.

**Repo :** https://github.com/jersou/studio-pack-generator

### Option A — Binaire précompilé (recommandé)

Télécharger depuis les [releases GitHub](https://github.com/jersou/studio-pack-generator/releases) :

| Plateforme | Binaire |
|------------|---------|
| Linux x86_64 | `studio-pack-generator-x86_64-linux` |
| Windows | `studio-pack-generator-x86_64-windows.exe` |
| macOS Apple Silicon | `studio-pack-generator-aarch64-apple` |
| macOS Intel | `studio-pack-generator-x86_64-apple` |

Placer le binaire dans `bin/` à la racine du projet ou dans le `PATH` système.

```bash
mkdir -p bin
curl -L https://github.com/jersou/studio-pack-generator/releases/latest/download/studio-pack-generator-x86_64-linux \
     -o bin/studio-pack-generator
chmod +x bin/studio-pack-generator
```

### Option B — Via Deno (pour dev)

```bash
# installer Deno
curl -fsSL https://deno.land/install.sh | sh

# lancer directement
deno run -A jsr:@jersou/studio-pack-generator "chemin/vers/dossier"
```

---

## 6. Architecture du projet Python

```
lunii-pack-generator/
├── pyproject.toml
├── README.md
├── bin/
│   └── studio-pack-generator          ← binaire externe (gitignore)
├── source/                            ← dossier source des MP3 (gitignore)
│   ├── 01 - Catégorie A/
│   ├── 02 - Catégorie B/
│   └── 03 - Catégorie C/
├── output/                            ← .zip généré (gitignore)
└── lunii_pack_generator/
    ├── __init__.py
    ├── cli.py                         ← point d'entrée Click
    ├── validator.py                   ← validation de l'arborescence source
    ├── generator.py                   ← appel subprocess studio-pack-generator
    └── utils.py                       ← helpers (détection OS, binaire, etc.)
```

---

## 7. Comportement attendu des modules

### `cli.py`
- Interface Click avec les options :
  - `--source` : chemin vers le dossier source (défaut : `./source`)
  - `--output` : dossier de sortie du `.zip` (défaut : `./output`)
  - `--bin` : chemin vers le binaire `studio-pack-generator` (défaut : `./bin/studio-pack-generator`)
  - `--lang` : langue TTS (défaut : `fr`)
  - `--delay/--no-delay` : ajouter 1 seconde de silence début/fin (défaut : activé)
  - `--auto-next/--no-auto-next` : enchaînement automatique à la fin d'une histoire (défaut : activé)
- Affichage Rich : arborescence des catégories et histoires détectées avant la génération.
- Confirmation utilisateur avant de lancer.

### `validator.py`
Valide **avant** de lancer la génération :
- Le dossier source existe.
- Il contient au moins 1 sous-dossier (catégorie).
- Chaque catégorie contient au moins 1 fichier `.mp3`.
- Aucun fichier MP3 n'est vide (taille > 0 octets).
- Les noms de dossiers sont préfixés numériquement (warning non bloquant sinon).
- Retourne un rapport structuré : nb catégories, nb histoires total, liste des warnings.

### `generator.py`
- Détecte l'OS pour choisir automatiquement le bon nom de binaire.
- Vérifie que le binaire est exécutable (et propose le `chmod +x` sinon).
- Construit et exécute la commande `subprocess.run(...)` avec les bons arguments.
- Capture stdout/stderr et les affiche en temps réel via Rich.
- Détecte le `.zip` généré, le déplace dans `output/`, affiche son chemin et sa taille.
- Lève une exception claire si le binaire est absent ou si la génération échoue.

### `utils.py`
- `detect_binary_path()` : cherche le binaire dans `./bin/`, puis dans le `PATH`.
- `get_platform_binary_name()` : retourne le nom du binaire selon `sys.platform`.
- `format_size(bytes)` : formatage lisible de la taille (Ko, Mo).

---

## 8. Commandes d'utilisation

```bash
# Activation du venv
source .venv/bin/activate

# Lancement basique
lunii-gen --source ./source

# Avec options explicites
lunii-gen \
  --source ./mes_histoires \
  --output ./dist \
  --lang fr \
  --delay \
  --auto-next

# Vérifier les dépendances système avant de lancer
lunii-gen --check-deps
```

---

## 9. `.gitignore`

```
.venv/
bin/studio-pack-generator*
source/
output/
__pycache__/
*.pyc
.pytest_cache/
```

---

## 10. Tests

```bash
uv run pytest
```

Tests à implémenter dans `tests/` :
- `test_validator.py` : cas nominal, dossier vide, MP3 manquants, noms sans préfixe.
- `test_utils.py` : détection binaire, formatage taille.
- `test_generator.py` : mock subprocess, vérification de la commande construite.

---

## 11. Hors scope

- Conversion audio (MP3 uniquement, déjà au bon format).
- Génération des images d'illustration (déléguée à ImageMagick via studio-pack-generator).
- Transfert USB vers la Lunii (fait manuellement depuis STUdio).
- Support RSS ou podcast.
- Interface graphique.
