# CONTREPOIDS

Un puits de mine vertical rempli de plateformes suspendues par des cordes qui
passent sur des poulies. Rien n'a de moteur : tout ne bouge que par difference
de poids entre deux plateformes liees par une meme corde. Vous incarnez un
mineur qui peut porter un seul objet a la fois, et votre propre corps compte
comme un poids des que vous vous tenez sur une plateforme. Atteignez la sortie
en haut du puits.

## Pitch

Douze niveaux de puzzle de contrepoids en 3D, dans la famille de GRAVITE NEUF
mais sans gravite orientable : le puits reste toujours vertical, la
difficulte vient de la chimie du poids (pierre, enclume, ballon, votre propre
corps) et de l'ordre des actions.

## Commandes

| Touche | Action |
| --- | --- |
| `Z` `Q` `S` `D` ou fleches | Se deplacer / monter-descendre d'une plateforme adjacente |
| `E` | Prendre / poser l'objet sous la main, ou pousser une enclume adjacente a niveau egal |
| `Espace` | Sauter d'un cran (pour rattraper une plateforme qui vient de monter) |
| `Ctrl`+`Z` | Annuler (illimite) |
| `R` | Recommencer le niveau |
| Souris (glisser) | Orbiter la camera |
| Molette | Zoomer |
| `I` `J` `K` `L` | Orbiter au clavier |
| Trackpad (balayage 2 doigts) | Orbiter (l'axe horizontal du geste l'emporte sur le zoom) |
| `Echap` | Pause |
| `M` | Couper le son |

## Regles

- Les hauteurs et les poids sont des nombres entiers. Chaque plateforme a une
  butee basse et une butee haute qu'elle ne peut jamais depasser.
- Une **corde simple** relie exactement deux plateformes via une poulie.
  Chaque changement de poids sur l'une des deux force une resolution
  immediate : `D = poidsA - poidsB`. Si `D > 0`, A descend et B monte de `D`
  crans (moins si une butee est atteinte avant). Si `D < 0`, l'inverse. Si
  `D == 0`, rien ne bouge, mais l'action qui a cause ce calcul reste
  executee : deplacer, prendre, poser ou pousser sont toujours valides des
  qu'ils sont physiquement possibles.
- Une **chaine de plusieurs plateformes** est simulee en faisant partager une
  meme plateforme a plusieurs cordes simples, jamais par un calcul a trois
  plateformes ou plus.
- Objets : la **pierre** (poids 1) et le **ballon** (poids -1, il allege) se
  portent. L'**enclume** (poids 3) ne se porte jamais : elle se pousse d'une
  plateforme a l'autre, strictement a niveau egal.
- Le mineur pese 2 des qu'il se tient sur une plateforme : monter dessus la
  fait descendre, il faut parfois sauter au bon moment.
- Le score compare le nombre d'actions au par du niveau (calcule hors ligne
  par un solveur) : medaille d'or a l'egal du par, argent a +1, bronze au dela.

## Notes techniques

- Zero build : ES modules natifs, aucune dependance externe.
- three.js r169 vendorise dans `vendor/three.module.js`.
- Zero asset binaire : toutes les textures sont peintes dans un `<canvas>` 2D
  au demarrage, tous les sons sont synthetises en Web Audio.
- Le modele de jeu (`src/shaft.js`) est pur (aucune dependance three.js), ce
  qui a permis de valider le par exact des douze niveaux avec un solveur en
  largeur hors ligne (`node tools/solve.mjs`) avant de les livrer.
- Progression sauvegardee dans `localStorage` sous le prefixe `contrepoids.`.
