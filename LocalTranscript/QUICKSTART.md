# 🚀 Guide de Démarrage Rapide

## Installation (5 minutes)

### Méthode Automatique (Recommandée)

1. **Double-cliquez sur `setup.bat`**
   - Créé l'environnement virtuel
   - Installe toutes les dépendances
   - Configure le projet

2. **Lancez l'application**
   - Double-cliquez sur `run.bat`
   - OU ouvrez PowerShell et tapez :
     ```bash
     venv\Scripts\activate
     python main.py
     ```

### Méthode Manuelle

```bash
# 1. Créer environnement virtuel
python -m venv venv

# 2. Activer
venv\Scripts\activate

# 3. Installer dépendances
pip install -r requirements.txt

# 4. Lancer
python main.py
```

## 📋 Cas d'Usage Rapides

### Cas 1 : Surveiller les Sorties de Vibe

**Objectif** : Copier automatiquement les transcriptions Vibe dans le presse-papier

1. Ouvrir Vibe et configurer un dossier de sortie (ex: `C:\Transcriptions`)
2. Lancer LocalTranscript :
   ```bash
   python main.py watch "C:\Transcriptions"
   ```
3. Utiliser Vibe pour transcrire
4. Le texte est automatiquement copié dans le presse-papier ✨

### Cas 2 : Transcrire un Fichier Sans Vibe

**Objectif** : Transcrire directement avec faster-whisper

```bash
# Transcription simple
python main.py transcribe "mon_audio.mp3"

# Avec sortie fichier
python main.py transcribe "conference.mp4" -o "transcription.txt"

# Générer des sous-titres
python main.py transcribe "video.mp4" -o "subs.srt" -f srt
```

### Cas 3 : Interface Graphique

**Objectif** : Utiliser l'interface visuelle

1. Lancer : `python main.py`
2. **Onglet "Surveillance Vibe"** :
   - Choisir dossier à surveiller
   - Cliquer "Démarrer"
   - Utiliser Vibe normalement

3. **Onglet "Transcription Directe"** :
   - Sélectionner fichier audio/vidéo
   - Choisir modèle (base recommandé)
   - Cliquer "Transcrire"

## ⚙️ Configuration Rapide

Éditer `config/settings.json` :

```json
{
  "whisper": {
    "model_size": "base",    // tiny, base, small, medium, large
    "language": "fr"          // fr, en, auto, etc.
  },
  "output": {
    "auto_clipboard": true,   // Copie auto dans presse-papier
    "notification_enabled": true
  }
}
```

## 🎯 Workflow Recommandé

### Pour Usage Quotidien avec Vibe

```
[Démarrage PC]
    ↓
[Lancer: python main.py watch "C:\Transcriptions"]
    ↓
[Utiliser Vibe normalement]
    ↓
[Transcription auto-copiée dans presse-papier]
    ↓
[Coller où vous voulez : Ctrl+V]
```

### Pour Transcription Occasionnelle

```
[Interface GUI: python main.py]
    ↓
[Onglet "Transcription Directe"]
    ↓
[Sélectionner fichier → Transcrire]
    ↓
[Copier résultat]
```

## 🔧 Personnalisation

### Changer la Taille du Modèle Whisper

Plus le modèle est grand, plus c'est précis mais lent :

- **tiny** : ~1 GB RAM, très rapide, moins précis
- **base** : ~1 GB RAM, bon compromis ⭐ RECOMMANDÉ
- **small** : ~2 GB RAM, plus précis
- **medium** : ~5 GB RAM, très précis
- **large** : ~10 GB RAM, maximum précision

Éditer `config/settings.json` :

```json
"whisper": {
  "model_size": "small"  // Changez ici
}
```

### Activer GPU (si NVIDIA)

Pour transcription ultra-rapide avec GPU :

```json
"whisper": {
  "device": "cuda",
  "compute_type": "float16"
}
```

**Prérequis** : CUDA Toolkit installé

## 🐛 Problèmes Courants

### "Module not found"

```bash
# Réinstaller les dépendances
venv\Scripts\activate
pip install -r requirements.txt
```

### Notifications ne s'affichent pas

```bash
pip install --upgrade win10toast-ng
```

### Transcription très lente

1. Utiliser un modèle plus petit (`tiny` ou `base`)
2. Ou activer GPU (si disponible)

### Vibe introuvable

Éditer le chemin dans `config/settings.json` :

```json
"vibe": {
  "executable_path": "C:\\Chemin\\Vers\\vibe.exe"
}
```

## 📚 Aide

- **Voir toutes les commandes** : `python main.py --help`
- **Aide surveillance** : `python main.py watch --help`
- **Aide transcription** : `python main.py transcribe --help`

## 🎉 Vous êtes Prêt !

Commencez par :

```bash
# Interface graphique (plus simple)
python main.py

# OU ligne de commande (plus rapide)
python main.py transcribe "test.mp3"
```

Bon courage ! 🚀
