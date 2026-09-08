# voice_bridge - parler et se faire répondre par Claude Code / Codex

Sortie audio en français pour les agents de code, sur Windows. L'entrée (dictée)
est déjà couverte par Handy ou par les modes vocaux natifs : ce dépôt s'occupe
de la moitié manquante, faire lire les réponses à voix haute.

## Trois cas, trois branchements

| Cas | Comment le texte arrive | Ce qu'il faut faire |
| --- | --- | --- |
| **Claude Code** | hook `Stop`, champ `last_assistant_message` | `install.ps1 -WireHooks`, rien d'autre |
| **Codex** | hook `Stop`, champ `last_assistant_message` | idem, **puis** accorder la confiance aux hooks (voir plus bas) |
| **Tout le reste** (Ollama, une API, un script) | aucun hook : on filtre la sortie | `... | .\vox.ps1` |

Les deux agents exposent bien le texte final du tour au hook, vérifié en session
réelle. Le payload Codex ressemble à ceci :

```json
{"session_id":"01a0821b-...","turn_id":"01a0821b-...",
 "transcript_path":"C:\\Users\\...\\rollout-2026-09-08T19-40-50-....jsonl",
 "cwd":"C:\\Dev\\squad-ai\\Brainstorming\\voice_bridge",
 "hook_event_name":"Stop","model":"gpt-5.5",
 "permission_mode":"bypassPermissions","stop_hook_active":false,
 "last_assistant_message":"le canal de sortie est lisible"}
```

Il n'y a donc pas à relire le transcript ni à espionner le terminal : le texte
est dans le payload. Claude Code fournit le même champ, plus `prompt_id` et
`effort`.

## Mise en place

```powershell
cd voice_bridge
.\install.ps1 -WithPocket -WireHooks   # moteurs + voix française + branchement
.\voice.ps1 on                         # active la lecture des réponses
```

`-WithPocket` installe Kyutai Pocket TTS dans `.venv-pocket` (PyTorch CPU,
environ 1 Go) et télécharge les poids français. Sans ce drapeau, seul Piper est
installé, et sa voix est nettement plus mécanique.

`install.ps1` sauvegarde `~/.claude/settings.json` et `~/.codex/hooks.json`
avant de les modifier, et n'ajoute que ses propres entrées. `.\install.ps1 -Unwire`
les retire.

**Étape obligatoire côté Codex.** Codex n'exécute que des hooks dont il a
mémorisé la signature. Après toute modification de `hooks.json`, lance `codex`
en interactif une fois : il affiche « Hooks need review » et il faut répondre
« Trust all and continue ». Sans ça il ignore **tous** les hooks, y compris ceux
qui marchaient avant, sans le moindre message. La confiance est stockée sous
forme de `trusted_hash` dans `config.toml`. Pour de l'automatisation,
`--dangerously-bypass-hook-trust` court-circuite la vérification.

## Lire la sortie de n'importe quel modèle

```powershell
ollama run ministral-3:8b "explique les hooks" | .\vox.ps1
codex exec "resume le diff" | .\vox.ps1 -Backend edge
```

`vox.ps1` réémet son entrée à l'identique puis la lit en entier, découpée en
morceaux enchaînés pour que le son démarre tout de suite. Un raccourci global :

```powershell
function vox { $input | & "C:\Dev\squad-ai\Brainstorming\voice_bridge\vox.ps1" @args }
```

## Activer / couper depuis Claude Code

La commande `/voix` bascule la lecture sans quitter la session :

| Frappe | Effet |
| --- | --- |
| `/voix` | bascule (activé <-> coupé) |
| `/voix on` | active |
| `/voix off` | coupe, et arrête la lecture en cours |
| `/voix status` | état du basculement, du moteur et des démons |

Elle vit dans `~/.claude/skills/voix/SKILL.md`. Le basculement s'exécute avant
même que le modèle ne réponde, donc il prend effet immédiatement, y compris sur
la réponse en cours.

Les raccourcis clavier de Claude Code ne peuvent pas servir ici : ils ne mappent
que des actions internes de l'interface, jamais une commande externe.

L'état est un simple fichier, `%LOCALAPPDATA%\voice_bridge\enabled`, donc il
survit aux redémarrages. Les démons de synthèse, eux, ne survivent pas : après un
redémarrage, lance `.\voice.ps1 start`, ou laisse Piper se relancer tout seul à
la première lecture.

## Utilisation en ligne de commande

| Commande | Effet |
| --- | --- |
| `.\voice.ps1 on` / `off` / `toggle` | lecture automatique des réponses |
| `.\voice.ps1 voices` | lister les 26 voix de Pocket TTS |
| `.\voice.ps1 demo` | écouter les voix candidates à la suite |
| `.\voice.ps1 use <moteur> [voix]` | figer le moteur et la voix |
| `.\voice.ps1 last` | relire la dernière réponse de ce dossier, à la demande |
| `.\voice.ps1 say "texte"` | dire une phrase |
| `.\voice.ps1 shut` | couper la lecture en cours |
| `.\voice.ps1 status` | état du moteur, des démons et du basculement |
| `.\voice.ps1 start` / `stop` | démons de synthèse seuls |

Pour un vrai bouton, associer `voice.ps1 last` à un raccourci global
(AutoHotkey, ou une tâche du terminal) :

```autohotkey
^!L::Run, powershell.exe -NoProfile -File C:\Dev\squad-ai\Brainstorming\voice_bridge\voice.ps1 last,, Hide
^!K::Run, powershell.exe -NoProfile -File C:\Dev\squad-ai\Brainstorming\voice_bridge\voice.ps1 shut,, Hide
```

## Ce qui est lu

Une réponse complète de Claude Code est illisible à voix haute. Par ordre de
priorité, `speak.py` lit :

1. le contenu d'une balise `<voix>...</voix>` écrite par l'agent,
2. sinon le dernier paragraphe, là où se trouve la conclusion,
3. tronqué sur une fin de phrase à `max_chars` (260 par défaut).

Le hook `UserPromptSubmit` apprend la convention `<voix>` à l'agent, mais
uniquement quand la voix est active : hors mode vocal, rien n'est injecté et
les réponses écrites ne changent pas.

### Régler ce que l'agent dit

Le texte de cette consigne vit dans **`consigne_vocale.md`**, à éditer
librement : ton, longueur, ce qu'il faut mentionner ou taire. Elle est relue à
chaque question, donc aucun redémarrage n'est nécessaire, et la modification
prend effet dès le message suivant.

Le hook renvoie la consigne via `[System.IO.File]::ReadAllText`, pas
`Get-Content -Raw` : ce dernier décore la chaîne de propriétés PowerShell
(`PSPath`, `PSProvider`…) que `ConvertTo-Json` sérialise en objet, alors que
`additionalContext` doit être une chaîne.

## Moteurs

| Backend | Où | Coût | Premier son | Qualité française |
| --- | --- | --- | --- | --- |
| `pocket` (défaut) | 100 % local, CPU | gratuit | **430 ms** | Kyutai Pocket TTS, 24 kHz, la meilleure |
| `piper` | 100 % local, CPU | gratuit | 290 ms | VITS 2022 à 22 kHz, mécanique |
| `edge` | cloud Microsoft, sans clé | gratuit | ~1,8 s | voix neurales Edge, très bonne |
| `sapi` | Windows, hors-ligne | gratuit | ~0,3 s | robotique |

Mesures sur i7-13700H, phrase de 76 caractères produisant 4,3 s d'audio.

Pocket génère à RTF 0,8, donc attendre le fichier complet coûterait 3,5 s de
silence. Le démon renvoie le PCM au fur et à mesure et `speak.py` le pousse
directement dans le lecteur : le premier son sort en 430 ms, et comme la
génération va plus vite que la lecture, elle ne décroche jamais.

Piper reste le plus rapide et le plus léger, utile si le CPU est déjà saturé.
Il passe par son démon résident : sans lui, le CLI recharge le modèle de 63 Mo
et coûte ~6 s par appel.

### Choisir sa voix

```powershell
.\voice.ps1 demo                          # écoute les 8 candidates à la suite
.\voice.ps1 use pocket estelle            # fige le choix
.\voice.ps1 use edge fr-FR-HenriNeural
.\voice.ps1 use piper fr_FR-tom-medium
```

`use` écrit `config.json` à côté de `speak.py` et redémarre le démon du moteur
concerné sur la nouvelle voix. Un démon ne tient qu'un modèle : il répond `409` si on lui
demande une autre voix, ce qui renvoie vers le CLI plutôt que de parler dans la
mauvaise voix sans le dire. `GET /health` annonce la voix chargée.

Le fichier se modifie aussi à la main :

```json
{
  "backend": "edge",
  "edge_voice": "fr-FR-HenriNeural",
  "edge_rate": "+15%",
  "max_chars": 260
}
```

### Les voix de Pocket TTS

`.\voice.ps1 voices` liste les **26 voix** livrées avec le modèle français,
13 féminines et 13 masculines. Ce sont des embeddings pré-calculés par Kyutai
pour `french_24l`, donc elles parlent toutes français, mais l'origine du
locuteur prédit l'accent : seule `estelle` vient d'une source française, les
`VCTK` sont des voix britanniques, `lola` est espagnole.

Le clonage depuis un `.wav` quelconque existe, mais il exige l'autre jeu de
poids, celui du dépôt `kyutai/pocket-tts`, qui est **sous accès contrôlé** :
accepter les conditions sur la page du modèle, puis définir `HF_TOKEN`. Sans
ça, `get_state_for_audio_prompt` échoue sur « could not download the weights
for the model with voice cloning ». Une fois débloqué, les 35 locuteurs
français du corpus CML-TTS (CC-BY) deviennent utilisables.

Voix Piper françaises disponibles au téléchargement : `siwis`, `tom`, `upmc`
(qualité `medium`), `gilles`, `mls`, `mls_1840` (qualité `low`). Voix Edge :
`Denise`, `Henri`, `Eloise`, `Vivienne` et `Remy` (ces deux dernières
multilingues).

## Pièges rencontrés

- **Double bind silencieux du port.** Sur Windows, `allow_reuse_address` (activé
  par défaut dans `http.server`) laisse un second démon se lier au même port sans
  erreur, et c'est l'ancien processus qui continue de répondre. `piper_server.py`
  le refuse explicitement.
- **Préchauffage ONNX obligatoire.** Si la toute première synthèse a lieu dans un
  thread de requête, ONNX Runtime installe son pool d'intra-op threads de travers
  et chaque appel coûte ~3,5 s au lieu de ~0,4 s, définitivement. Le démon
  synthétise une phrase bidon dans le thread principal avant d'ouvrir le port.
- **PATH des hooks.** `uv tool install` pose ses shims dans `~/.local/bin`, qui
  n'est pas dans le PATH d'un hook. `speak.py` les cherche explicitement.
- **Les deux agents n'ont pas le même format de hook.** Claude Code veut la forme
  exec (`command` + tableau `args`), Codex veut une seule chaîne shell. Donner la
  forme de l'un à l'autre produit un `hook: Stop Failed` sans autre explication.
  `install.ps1` génère la bonne forme par cible.
- **Confiance des hooks Codex.** Un hook non approuvé n'est pas exécuté, et rien
  n'est affiché. Un `hooks.json` correct qui « ne fait rien » est presque toujours
  ça.
- **stdin arrive en cp1252.** Python décode l'entrée standard avec la page de
  codes ANSI sous Windows : un texte UTF-8 piped ressort en mojibake, et
  ré-encodé il double (`é` devient `Ã©`). `speak.py` lit `sys.stdin.buffer` et
  décode en UTF-8 explicitement ; le hook force `StandardInputEncoding` en UTF-8.
- **Console cp1252 en sortie aussi.** `--dry-run` écrit des octets UTF-8 bruts,
  sinon les accents ressortent en mojibake.

## Fichiers

- `speak.py` - extraction du texte à dire, synthèse, lecture, `--tee`, `--stop`
- `pocket_server.py` - démon Kyutai Pocket TTS, avec `/stream` en PCM continu
- `piper_server.py` - démon qui garde la voix Piper en mémoire
- `voice.ps1` - pilote (on/off/last/say/status)
- `vox.ps1` - filtre pipeline pour les modèles sans hook
- `install.ps1` - outils, voix, branchement des agents
- `hooks/stop_speak.ps1` - lit la réponse quand l'agent a fini
- `hooks/prompt_context.ps1` - enseigne la convention `<voix>`
