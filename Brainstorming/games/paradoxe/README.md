# PARADOXE

Un puzzle 3D de cooperation avec soi-meme. Chaque arene vous laisse une poignee de
secondes. Quand le temps est ecoule, ou quand vous rembobinez, tout revient a zero et un
**clone** rejoue exactement ce que vous venez de faire, image par image. Puis un deuxieme,
puis un troisieme. Le clone 1 maintient le bouton qui ouvre la porte que le clone 2
franchit pour poser la caisse sur la plaque que vous utilisez a la passe suivante. Empechez
un clone de refaire son geste et la ligne de temps casse: paradoxe, la passe est perdue.

Quatorze arenes, trois mecaniques enseignees sans un mot de tutoriel, un rembobinage
instantane et une annulation illimitee: la difficulte vient de la planification, jamais de
la punition.

## Commandes

| Touche | Action |
|---|---|
| `Z` `Q` `S` `D` ou les fleches | Se deplacer (relatif a la camera) |
| `ESPACE` | Sauter |
| `E` | Prendre / poser une caisse |
| `R` | Rembobiner tout de suite (la passe devient un clone) |
| `CTRL` + `Z` | Annuler le dernier clone enregistre |
| `T` | Recommencer le niveau de zero |
| Souris (glisser) | Orienter la camera |
| `I` `J` `K` `L` | Orienter la camera sans souris (pave numerique aussi) |
| Molette | Zoomer (glissement lateral du pave tactile: pivoter, `MAJ` + glissement: incliner) |
| `ECHAP` | Pause |
| `M` | Couper le son |

## Regles

- **Une passe** dure de 12 a 20 secondes selon l arene. A la fin (ou sur `R`), elle devient
  un clone qui rejouera la meme chose a chaque passe suivante.
- **Rembobiner tot est une tactique**: passe la fin de sa bande, un clone se fige sur place.
  Une passe de deux secondes fabrique donc une statue solide exactement ou vous voulez.
- **Les clones sont solides**: on leur monte sur la tete, ils bloquent un couloir, ils
  appuient sur les boutons.
- **Boutons** (ronds, oranges): ouverts tant qu un corps ou une caisse est dessus.
  **Plaques** (carrees, violettes): il faut une caisse, un corps ne suffit pas.
  Certaines portes demandent plusieurs appuis simultanes.
- **Sol fragile** (dalles claires): cede quelques instants apres le passage. Il ne se
  reconstruit qu au rembobinage.
- **Teleporteurs**: relient deux dalles, la caisse portee voyage avec vous.
- **La sortie n accepte que le joueur de la passe en cours.** Un clone ne finit rien.
- **Paradoxe**: si un clone ne peut pas reproduire un geste enregistre (prendre sa caisse,
  atteindre son bouton, passer son teleporteur) ou s il est detourne longtemps de sa
  trajectoire, le niveau echoue avec la raison exacte. `CTRL`+`Z` annule le clone fautif.
- **Medaille** quand le niveau est resolu avec au plus le nombre de clones vise.
- La progression et les meilleurs scores sont conserves dans le `localStorage` sous les
  cles `paradoxe.progress` et `paradoxe.best`.

## Notes techniques

- **Zero build, zero asset binaire, zero reseau.** ES modules natifs, three.js r169
  vendorise dans `vendor/`, importmap dans `index.html`. Toutes les textures sont dessinees
  dans un canvas 2D au demarrage, tous les sons sont synthetises en Web Audio.
- **Simulation a pas fixe de 1/60 s** avec accumulateur, le rendu interpole entre les deux
  derniers etats. C est la condition de correction du jeu: sans pas fixe le rejeu derive et
  les puzzles deviennent injouables.
- **On enregistre des entrees, jamais des positions**: un octet de bits clavier et un octet
  de cap camera quantifie par tick. Rejouer, c est renourrir la meme simulation. Les
  positions sont enregistrees en parallele mais servent uniquement au rembobinage visuel et
  a la detection de blocage.
- **Determinisme**: aucun `Math.random` dans la simulation, aucune dependance au temps reel,
  ordre d iteration stable. Les acteurs sont mis a jour du plus ancien au plus recent, le
  joueur en dernier: c est ce qui garantit que deux corps se resolvent toujours dans le
  meme ordre d une passe a l autre.
- **Rendu**: `InstancedMesh` pour les sols, blocs et murs (une passe de dessin par classe),
  materiau `ShaderMaterial` a fresnel pour les clones (fentes chromatiques et scanlines),
  trainee fantome instanciee partagee. Moins de soixante appels de dessin par image.
- Les murs sont dessines a 2.2 de haut mais simules a 3.6: la marge invisible empeche
  d atterrir sur un mur apres un saut depuis un bloc de 2, sans emmurer la camera.

## Lancer

Le jeu est servi par la console arcade du depot:

```
python games/arcade/arcade.py
```

puis choisir PARADOXE. N importe quel serveur de fichiers statiques fait l affaire, il faut
juste du HTTP (les modules ES ne se chargent pas depuis `file://`).
