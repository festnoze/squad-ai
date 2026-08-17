# RESONANCE

Puzzle d'interférences en 3D. Une caverne de cristal, un bassin de mercure où
les ondes se propagent à vue, et des diapasons à poser sur la grille. Chaque
diapason émet une onde entretenue à sa fréquence ; les ondes se réfléchissent
sur les parois et interfèrent : là où elles arrivent en phase, l'amplitude
s'additionne (ventres brillants), en opposition elles s'annulent (noeuds
sombres). Objectif : faire éclater tous les cristaux cibles sans jamais faire
éclater un cristal interdit. Douze chambres, annulation illimitée, aucune
contrainte de temps. Le motif d'interférence EST le jeu.

## Lancer

Le jeu est servi par la console arcade du dépôt :

```
python games/arcade/arcade.py
```

puis choisir RESONANCE (http://localhost:8088/g/resonance/). Zéro build, zéro
dépendance : ES modules natifs et three.js r169 vendorisé dans `vendor/`.

## Commandes

| Entrée | Effet |
|---|---|
| 1 / 2 / 3 | Choisir la fréquence à poser (grave, médium, aigu) |
| Clic gauche | Poser le diapason choisi, ou sélectionner un diapason posé |
| G / clic droit | Tourner la phase du diapason (quart de période) |
| F / molette sur le diapason sélectionné | Changer sa fréquence (si le stock le permet) |
| Suppr / clic milieu | Retirer le diapason visé |
| Ctrl+Z | Annuler (illimité, restaure aussi les cristaux brisés) |
| R | Recommencer le niveau |
| Souris glissée / IJKL | Orbiter (IJKL : position physique stable AZERTY et QWERTY) |
| Molette | Zoomer (un trackpad qui glisse horizontalement oriente la caméra) |
| N / P | Niveau suivant / précédent débloqué |
| M | Couper le son |
| Échap | Pause |

## Règles

- La simulation tourne en continu : chaque pose, retrait ou réglage réinjecte
  l'onde immédiatement, sans bouton « lancer ». Un diapason retiré laisse son
  onde s'éteindre en une à deux secondes.
- Un cristal éclate quand l'amplitude locale **dans sa bande de fréquence**
  dépasse son seuil pendant 1,5 s continue. Sa jauge (anneau au sol + coeur
  lumineux) montre la charge monter ; celle des cristaux interdits (rouges,
  pictogramme au sol) aussi : on voit le danger avant la casse.
- Pas de victoire volée : tant qu'un cristal interdit se charge, le niveau
  n'est pas validé. S'il éclate, Ctrl+Z le restaure, R recommence.
- Les parois (bord et intérieures) réfléchissent les ondes : les échos
  participent aux interférences. Les mousses absorbent. Les résonateurs
  écoutent une bande et ré-émettent dans une autre : ce sont des relais.
- Médailles : or au nombre optimal de diapasons (celui de la solution de
  référence), argent à +1, bronze au-delà. Progression et records dans
  `localStorage` sous les clés `resonance.*`.

## Notes techniques

- **Simulation** (`src/wave.js`, pur, importable sous Node) : équation d'onde
  2D par différences finies, grille 96x96, trois champs Float32Array (un par
  bande), buffers permutés sans allocation, pas de temps fixe (1/60 s, au plus
  un pas par frame rendue) ; le motif est une fonction pure du compteur de pas,
  identique quelle que soit la cadence d'image. Bords et parois en condition
  de Neumann (réflexion), mousses par amortissement local fort, résonateurs
  par couplage additif entre champs. Amortissement global 0,99 mesuré pour un
  régime établi lisible en moins de deux secondes.
- **Niveaux** (`src/levels.js`) : 12 niveaux en données avec solution de
  référence. `node tools/validate_levels.mjs` rejoue chaque solution dans la
  vraie simulation et vérifie cibles brisées / interdits épargnés / stock /
  par. `tools/rms_map.mjs` imprime la carte d'amplitude mesurée qui a servi à
  placer cristaux et seuils (jamais au doigt mouillé). Les niveaux-leçons ont
  aussi été passés au crible d'un balayage exhaustif des poses à un seul
  diapason pour vérifier que la leçon ne se contourne pas.
- **Rendu** : la surface est un plan de 96x96 sommets dont le vertex shader
  lit une DataTexture flottante (RGB = les trois champs, A = murs/mousses) ;
  fragment shader avec les chunks `tonemapping_fragment` / `colorspace_fragment`
  (sinon la surface rend plus sombre et plate que le décor, piège connu du
  dépôt). Cristaux, anneaux de charge, diapasons, halos et éclats sont des
  `InstancedMesh` ; les éclats sont des tétraèdres instanciés, jamais des
  `THREE.Points` (piège de calibrage connu du dépôt). Aucune texture binaire :
  tout est canvas 2D ; tout le son est Web Audio synthétisé (contexte créé au
  premier geste).
- Les actions pendant une animation (éclat, transition) ne sont jamais
  bloquées ni jetées : la simulation reste vivante et exécute tout ce qui est
  physiquement possible ; seul un refus physique (case occupée, stock épuisé)
  existe, toujours avec toast + son.
- La boucle rAF dort quand l'onglet est masqué et réarme l'horloge au retour.
- `window.game` + `window.__ready` exposent les hooks de test du dépôt
  (voir `docs/CONTRACTS.md`), dont `measureLuminance()` qui lit le framebuffer
  et renvoie la luminance moyenne (seuil de lisibilité mesuré, pas estimé).
