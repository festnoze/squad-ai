# MAREE

Une chambre rocheuse inondable. Vous ne controlez jamais votre explorateur : vous
controlez le niveau de l'eau, bassin par bassin, et il se debrouille seul.

## Le jeu

Un petit explorateur marche en permanence vers son drapeau-objectif. Il marche sur
le sol sec, la glace ou une caisse de bois qui affleure ; il nage des que l'eau lui
monte au cou ; il attend patiemment devant un obstacle ou un gouffre plutot que de
s'y jeter ; il ne se noie que s'il reste **entierement** submerge plus de 3 secondes
d'affilee. Votre seul pouvoir est de monter ou descendre le niveau de l'eau de
chaque bassin, et d'ouvrir ou fermer les vannes qui les relient.

## Commandes

| Touche / geste | Effet |
| --- | --- |
| Clic sur un plan d'eau | Selectionner ce bassin |
| Touches `1`-`4` | Selectionner un bassin au clavier |
| `Fleche haut` / `Fleche bas` | Monter / descendre le bassin selectionne d'un cran |
| Molette (verticale) | Meme chose que les fleches |
| Clic sur une vanne | L'ouvrir ou la fermer |
| `Ctrl+Z` | Annuler (illimite) |
| `R` | Recommencer le niveau |
| `N` / `P` | Niveau suivant / precedent (parmi ceux debloques) |
| Glisser la souris | Orbiter la camera |
| `Maj` + molette | Zoomer / dezoomer |
| Glissement a deux doigts (trackpad) | Orbiter la camera |
| `I` `J` `K` `L` | Orbiter au clavier |
| `Echap` | Pause |
| `M` | Couper le son |

## Regles

- **Bois flottant** : suit toujours la surface de son bassin, monte et descend avec
  elle. Une fois qu'elle affleure ou qu'elle depasse un support, c'est une marche.
- **Pierre coulante** : posee au fond d'un bassin des la creation du niveau, elle ne
  bouge jamais. Elle offre une marche fixe, mais si le bassin monte trop, cette
  marche se retrouve trop profonde et devient dangereuse : l'explorateur refuse d'y
  passer tant que l'eau n'est pas redescendue a une profondeur sure.
- **Vanne** : relie deux bassins adjacents. Ouverte, ils partagent desormais un seul
  niveau d'eau (modifier l'un modifie l'autre - a l'ouverture, les deux bassins sont
  ramenes au niveau le plus bas des deux). Fermee, ils redeviennent independants,
  geles chacun a leur niveau du moment.
- **Glace** : dans un bassin qui gele, une eau stable a un palier pendant 2 secondes
  de simulation durcit en un plancher de glace permanent a cette hauteur - il ne
  disparait jamais, meme si l'eau redescend ensuite (ou remonte trop haut et le
  recouvre, auquel cas il redevient une profondeur comme une autre).
- **Chaque geste compte** : un changement de niveau d'eau ou une vanne actionnee
  compte comme une action pour le score, meme si rien ne bouge visiblement ce
  coup-ci. La seule action gratuite est de redemander un niveau deja actif.
- **Jamais de punition** : annulation illimitee, recommencer est instantane.

## Score

Le nombre d'actions (changements de niveau + vannes) est compare au par du niveau :
medaille d'or a l'egal du par, argent a +1, bronze au-dela.

## Notes techniques

- Zero build : modules ES natifs, three.js r169 vendorise dans `vendor/`.
- Zero asset binaire : toutes les textures sont peintes sur un `<canvas>` 2D
  (`src/textures.js`), tout le son est synthetise en Web Audio (`src/audio.js`).
- Simulation pure et sans dependance a three.js dans `src/world.js`, `src/water.js`,
  `src/pathing.js` et `src/explorer.js` - verifiable hors navigateur avec Node.
- Progression et preferences audio dans `localStorage`, prefixees `maree.`.
- Voir `docs/CONTRACTS.md` pour les signatures publiques de chaque module.

## Lancer le jeu

Servir ce dossier en HTTP (l'arcade du depot le fait automatiquement) et ouvrir
`index.html`. Un navigateur avec WebGL2 est necessaire.
