# GRAVITE NEUF

Une structure de cubes flotte dans le vide. Vous etes le cube dore, et vous ne le deplacez
jamais : vous choisissez ou est le bas. Tout ce qui n'est pas fixe tombe alors dans cette
direction, jusqu'a rencontrer un obstacle, et la camera roule avec le monde pour que le
nouveau bas soit toujours en bas de l'ecran. Quatorze niveaux, un sokoban a six gravites,
zero punition : chaque erreur s'annule d'une touche, et chaque niveau affiche le nombre de
coups optimal pour ceux qui veulent la medaille.

Trois dimensions, six boutons, et pourtant la difficulte ne vient jamais de l'adresse :
elle vient de la question "si je bascule maintenant, ou tombe la caisse ?".

## Commandes

| Touche | Effet |
|---|---|
| Fleches, ou `Z` `Q` `S` `D` | Gravite horizontale, **relative a la camera** (fleche haut = la gravite part vers le fond de l'ecran) |
| `A` ou `Espace` | Gravite vers le haut de l'ecran |
| `E` ou `Maj` | Gravite vers le bas de l'ecran |
| `Ctrl` + `Z`, `U`, `Retour arriere` | Annuler (illimite) |
| `R` | Recommencer le niveau |
| `N` / `P` | Niveau suivant / precedent parmi ceux debloques |
| Souris glissee | Orbiter autour de la structure |
| Molette | Zoomer |
| `Echap` | Pause |
| `M` | Couper le son |

Les commandes de gravite sont recalculees a chaque appui a partir de l'orientation reelle
de la camera : tourner autour de la structure ne retourne jamais les touches.

Les six directions sont **toujours** acceptees. Une bascule vers laquelle rien ne peut
tomber reste un coup legal : le monde pivote quand meme, et c'est souvent exactement ce
qu'il faut pour preparer la suivante. La seule demande sans effet est celle qui redemande
la direction ou la gravite pointe deja ; elle ne coute rien. Une touche pressee pendant la
bascule n'est pas perdue, elle part des que le monde s'immobilise.

## Regles

- **Mobiles** : le cube joueur, les caisses, les cles. Ils tombent tous, ensemble, a chaque
  bascule, une case a la fois, jusqu'a rencontrer un obstacle.
- **Fixes** : les murs, la sortie (traversable), la glu, les piques, les plaques de
  pression (traversables) et les grilles colorees.
- **Glu** : un mobile qui vient se poser contre un bloc de glu y reste colle
  **definitivement**. C'est la seule facon de fabriquer une plateforme qui ne tombera plus.
- **Piques** : un mobile qui vient se poser contre les piques est detruit.
- **Plaques et grilles** : une grille est ouverte tant qu'un mobile vivant occupe une
  plaque de sa couleur. Une caisse collee sur une plaque ouvre la grille pour toujours.
- **Cles** : une cle est ramassee quand le cube joueur s'immobilise sur une case
  adjacente. La case liberee peut relancer la chute dans le meme mouvement, ce qui fait des
  cles d'excellents butoirs a usage unique.
- **Le vide** : un mobile qui sort de la boite est perdu. Le joueur ou une cle perdus font
  echouer le niveau (message explicite, `Ctrl`+`Z` pour revenir en arriere). Une caisse
  perdue est seulement une caisse perdue.
- **Victoire** : le cube joueur s'immobilise sur la sortie, toutes les cles ramassees.

Les trois premiers niveaux enseignent une mecanique chacun (basculer, les caisses, la
glu), puis viennent les cles, les piques, les plaques, la verticalite et leurs
combinaisons.

## Notes techniques

- **Zero build, zero asset binaire, zero reseau.** ES modules natifs, three.js r169
  vendorise dans `vendor/`, toutes les textures peintes dans un `<canvas>` 2D au demarrage,
  tous les sons synthetises en Web Audio, toute la geometrie generee en code.
- **Simulation entierement discrete et deterministe.** `src/world.js` et `src/gravity.js`
  n'importent pas three : ils sont charges tels quels par un solveur hors ligne (parcours
  en largeur sur les six directions) qui verifie que chaque niveau est resoluble et calcule
  son `par`. Les quatorze `par` publies par le jeu sortent de ce solveur, pas d'une
  estimation.
- **Undo** = une pile de clones complets du monde. La grille fait quelques centaines de
  cases : c'est gratuit, donc illimite.
- **Rendu** : un `InstancedMesh` par type de bloc fixe (une quinzaine d'appels de dessin
  pour tout un niveau), un `Mesh` par mobile. Les aretes des cubes sont cuites dans la
  texture, ce qui evite un `LineSegments` par bloc.
- **Camera** : la structure vit dans un `Group` dont le quaternion est interpole en 400 ms
  a chaque bascule. Le dome de ciel, lui, reste fixe en espace ecran et change de teinte
  selon l'axe de gravite : c'est le repere d'orientation permanent.
- **Progression** en `localStorage`, sous les cles `gravite_neuf.progress` et
  `gravite_neuf.audio`.

## Lancer

Deposer le dossier dans `games/` : la console arcade (`games/arcade/arcade.py`, port 8088)
le detecte toute seule. Sinon, n'importe quel serveur statique servant ce dossier fait
l'affaire (les modules ES exigent HTTP, pas `file://`).
