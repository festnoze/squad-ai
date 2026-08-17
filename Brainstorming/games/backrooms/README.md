# BACKROOMS

Un dedale infini de salles anormales : trouvez la sortie de chaque Niveau
avant qu'une silhouette noire ne vous trouve.

Vous avez glisse hors de la realite dans un ensemble de salles vides qui se
ressemblent toutes, inspire de l'univers internet des Backrooms. Douze
Niveaux, chacun avec son architecture et sa palette canoniques (salles
jaunes moisies, entrepot, tuyaux et tunnels, sous-sol electrique, cuisine
industrielle sans fin, noir absolu a la lampe torche, poolrooms, bureaux
abandonnes, descente finale). Certains Niveaux ajoutent une entite noire
humanoide qui patrouille et vous traque au bruit et a la vue. Aucune arme :
fuir, se cacher, ou faire moins de bruit sont les seules reponses.

## Lancer le jeu

Zero build, zero dependance. Servez ce dossier en HTTP (n'ouvrez pas
`index.html` en `file://`, les ES modules et l'importmap l'exigent) :

```
python -m http.server 8080
```

puis ouvrez `http://localhost:8080/`. Dans l'arcade de ce depot (`games/arcade`),
le jeu est expose automatiquement des que ce dossier est present sous `games/`.

## Commandes

| Touche | Action |
|---|---|
| `Z` `Q` `S` `D` ou fleches | Se deplacer |
| Souris (pointeur verrouille) | Regarder |
| Glisser-souris (si le pointeur n'est pas verrouille) | Regarder |
| `J` `L` / `I` `K` | Regarder au clavier (lacet / tangage), toujours actif |
| `Maj` | Courir (fatigue l'endurance, augmente fortement le bruit) |
| `Ctrl` | S'accroupir (silencieux, plus lent) |
| `E` | Interagir : ouvrir une porte, ramasser un objet, allumer/eteindre la lampe |
| `R` | Recommencer entierement le Niveau courant |
| `M` | Couper le son |
| `Echap` | Pause (libere le pointeur, regle la sensibilite souris et l'inversion verticale) |

## Regles

- Chaque Niveau a une sortie clairement distincte (un panneau vert lumineux
  "SORTIE"), jamais une porte identique aux autres.
- Un carnet ou une pile ramassable au sol donne un indice (direction
  approximative de la sortie, ou de l'autonomie de lampe), jamais le chemin
  exact.
- Toucher l'entite ne met jamais fin a la partie : vous etes renvoye au
  dernier point de reperage (un flash d'ecran bref, un son distinct), et le
  compteur de rencontres du Niveau augmente. Au-dela d'un seuil raisonnable
  de rencontres, le jeu vous suggere une reprise complete (`R`), sans jamais
  l'imposer.
- Medaille par Niveau : **or** si termine sous le temps cible sans aucune
  rencontre, **argent** si termine sans avoir jamais utilise `R`, **bronze**
  sinon.
- La progression (dernier Niveau atteint, meilleur temps, medaille et
  rencontres par Niveau) est sauvegardee dans `localStorage`, sous des cles
  prefixees `backrooms.` (l'origine est partagee avec les autres jeux de
  l'arcade).

## Notes techniques

- **Zero build** : ES modules natifs, `three.js` r169 vendorise dans
  `vendor/three.module.js`, importe via l'importmap de `index.html`. Aucun
  addon `three/examples/jsm/*`, aucun bundler, aucun CDN.
- **Zero asset binaire** : toutes les textures sont dessinees dans un
  `<canvas>` 2D (`src/textures.js`), tous les sons sont synthetises en Web
  Audio (`src/audio.js`), toute la geometrie des Niveaux est generee en code
  (`src/render/maze.js`).
- **Dedale procedural deterministe** : chaque Niveau est une grille de tuiles
  batie a partir de salles rectangulaires reliees par des couloirs, generee
  par un PRNG `mulberry32` a graine fixe (`src/maze.js`). `tools/validate_levels.mjs`
  verifie hors-ligne que les 12 Niveaux ont un chemin garanti entre le depart
  et la sortie, qu'aucune salle n'est isolee et que les points de patrouille
  de l'entite sont tous relies au reste du dedale.
- **Simulation a pas fixe** (`1/60 s`, accumulateur) pour le deplacement du
  joueur, l'IA de l'entite et la detection : le jeu se comporte pareil quelle
  que soit la cadence d'image. Le rendu (regard, animations cosmetiques,
  audio) tourne a la cadence d'affichage avec interpolation de position. La
  boucle se met en veille quand l'onglet est cache et remet l'horloge a
  l'heure au retour, pour eviter tout saut brutal de l'entite.
- **Budget de rendu** : murs/sol/plafond en `InstancedMesh` (un draw call
  chacun par Niveau), tubes fluorescents en simples plans emissifs (jamais de
  `PointLight` par tube), une unique lumiere dynamique dans tout le jeu (la
  lampe torche du joueur, en `SpotLight`, uniquement au Niveau "Noir absolu").
- **Controleur FPS** : pointeur verrouille en mode principal, avec un repli
  clavier (`J`/`L`/`I`/`K`) et un repli glisser-souris (deltas `clientX/Y`,
  actif uniquement hors verrouillage) pour rester jouable si le pointer lock
  echoue.

## Structure

```
index.html            importmap, DOM du HUD et des ecrans, filet anti-ecran-noir
styles.css             tout le style
arcade.json            metadonnees pour la console arcade
vendor/three.module.js copie vendorisee de three.js r169
src/main.js            boucle, machine a etats, orchestration
src/maze.js            grille de tuiles, generation deterministe, BFS (pur)
src/levels.js          les 12 Niveaux en donnees + palettes de theme (pur)
src/entity.js          machine a etats patrouille/chasse/recherche (pur)
src/player.js          controleur FPS, collision, endurance, bruit (pur)
src/camera.js          regard FPS : souris, clavier, glisser-souris
src/input.js           clavier/souris/pointer lock
src/textures.js        toutes les textures canvas, par theme
src/audio.js           tous les sons synthetises
src/hud.js             DOM du HUD et des ecrans
src/render/scene.js    renderer, camera, scene
src/render/maze.js     geometrie du dedale (InstancedMesh), portes, sortie, objets
src/render/entity.js   silhouette de l'entite
src/render/flashlight.js lampe torche du joueur
tools/validate_levels.mjs verification hors-ligne des 12 Niveaux
docs/CONTRACTS.md      signatures publiques des modules
```
