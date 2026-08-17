# AIGUILLAGE

Poste d'aiguillage de nuit, en 3D isometrique orbitable. Vous ne conduisez
aucun train et vous ne deplacez aucun avatar : votre seule interaction est de
cliquer sur les aiguillages du reseau pour que chaque train colore ressorte
par la sortie de sa couleur, sans collision et sans retard.

## Pitch

Une gare de triage la nuit. Des trains entrent par des points d'entree a
intervalles de plus en plus rapproches. Chaque train doit ressortir par la
sortie de sa couleur. Un aiguillage bascule toujours au clic, meme si un
train roule dessus a l'instant meme : sa route n'est figee que lorsque son
avant franchit reellement le point de decision.

## Commandes

| Entree | Effet |
|---|---|
| Clic gauche sur un aiguillage | Bascule l'aiguillage (toujours accepte) |
| Clic sur une voie d'attente occupee (ou son entree) | Renvoie le train en sens inverse |
| Glisser la souris (clic gauche ou molette cliquee) | Oriente la camera |
| Molette | Zoom avant/arriere |
| Glissement lateral a deux doigts (trackpad) | Oriente la camera |
| `I` `J` `K` `L` | Oriente la camera au clavier |
| `Espace` ou bouton dedie | Active/desactive la pause tactique (gele les trains, pas l'horloge) |
| `R` | Recommence le niveau instantanement |
| `M` | Coupe le son |
| `Echap` | Menu pause |

## Regles

- **Un clic sur un aiguillage bascule toujours sa position.** Il n'existe
  aucun etat qui refuse le clic : au pire, basculer un aiguillage deja dans
  la position demandee ne change rien.
- Le choix de voie d'un train n'est fige qu'au moment ou son avant franchit
  le point de decision de l'aiguillage. Basculer avant ce franchissement
  change la suite du train engage ; basculer apres n'affecte que les
  trains suivants.
- Deux trains ne peuvent jamais se toucher par derriere : un train ralentit
  et s'arrete automatiquement derriere un autre sur le meme troncon. Une
  collision ne survient que si deux trains se retrouvent nez a nez sur le
  meme troncon (typiquement une voie d'attente rappelee au mauvais moment).
  Une collision declenche un replay au ralenti centre sur le point d'impact
  puis l'echec du niveau, reseau intact pour recommencer.
- Un train livre a la mauvaise sortie termine egalement le niveau : c'est
  toujours une consequence directe et lisible d'un aiguillage mal regle.
- Un passage a niveau ferme force les trains a s'arreter en file avant la
  barriere, jamais de collision forcee contre elle. Les horaires de
  fermeture sont fixes et deterministes, jamais aleatoires.
- Une rame double (deux wagons colores lies) se separe automatiquement des
  que son avant franchit l'aiguillage de triage prevu par le niveau. La
  seconde moitie ne franchit ce meme aiguillage que quelques secondes plus
  tard : le rebasculer entre les deux passages envoie chaque moitie vers une
  sortie differente.
- 10 secondes de pause tactique par niveau, cumulables, geler les trains
  (pas l'horloge des aiguillages ni des passages a niveau) pour reflechir.
- Etoiles : 3 si tous les trains attendus sont livres sans le moindre
  retard, 2 ou 1 selon la part de retards, 0 en cas d'echec.

## Niveaux

12 postes de dispatching, difficulte croissante :

1. Premier aiguillage - un aiguillage, deux sorties.
2. Convergence - deux voies fusionnent avant de se separer par couleur.
3. Voie d'attente - stationner puis rappeler un train.
4. Passage a niveau - horaire de fermeture fixe.
5. Triage aux trois couleurs - siding, passage a niveau et 3 couleurs.
6. Rame double - separation automatique au triage.
7. Triage a trois entrees - trois spawns, quatre aiguillages.
8. Nuit chargee - passage a niveau, voie d'attente, cadence soutenue.
9. Grand triage - quatre couleurs, cinq aiguillages.
10. Rames doubles serrees - rames doubles, passage a niveau, voie d'attente.
11. Reseau tentaculaire - grand reseau, deux rames doubles.
12. Poste central - tout combine, cadence la plus serree.

## Notes techniques

- Zero build : ES modules natifs, `three.js` r169 vendorise dans
  `./vendor/three.module.js`, aucun addon `three/examples/jsm/*`.
- Zero asset binaire : toutes les textures sont dessinees dans un canvas 2D
  (`src/textures.js`), tout le son est synthetise en Web Audio
  (`src/audio.js`), toute la geometrie est generee en code.
- Simulation a pas de temps fixe, pure et sans dependance a `three`
  (`src/network.js`, `src/trains.js`) : le comportement (arrivees,
  collisions, aiguillages) est reproductible d'une execution a l'autre.
  Les plannings de spawn sont des tableaux de donnees deterministes
  (`src/schedule.js`, `src/levels.js`), jamais du hasard.
- Progression et meilleurs scores sauvegardes dans `localStorage`
  (`aiguillage.progress`, `aiguillage.scores`, `aiguillage.audio`).
- Sert de dossier statique : ouvrir via l'arcade (`games/arcade`, port 8088)
  ou n'importe quel serveur HTTP statique pointe sur ce dossier. Ouvrir
  `index.html` directement en `file://` casse les modules ES et l'importmap.

## Structure

```
index.html            importmap, DOM du HUD et des ecrans, filet anti-ecran-noir
styles.css             tout le style
src/main.js            boucle, machine a etats, orchestration
src/network.js         graphe pur (noeuds, segments, aiguillages, passages a niveau)
src/trains.js           simulation pure a pas fixe (aucune dependance a three)
src/schedule.js         lecteur de planning de spawn deterministe
src/levels.js           12 niveaux (topologie + planning) et leur generateur
src/spline.js           spline a abscisse curviligne (three)
src/camera.js           camera orbitale (souris, molette, trackpad, clavier)
src/input.js            pointeur, clavier, trackpad
src/hud.js              DOM du HUD et des ecrans (presentation pure)
src/audio.js            Web Audio pur
src/replay.js           dramatisation camera du replay au ralenti
src/render/scene.js     renderer, ciel nocturne, lumieres
src/render/track.js     rails, ballast, traverses, aiguillages, passages a niveau
src/render/trains.js    maillages de trains synchronises sur la simulation
docs/CONTRACTS.md       signatures publiques de chaque module
```
