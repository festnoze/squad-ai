# VIEWPOINT

Puzzle game 3D a la premiere personne en Godot 4, inspire de la mecanique
centrale de Viewfinder : les photos trouvees dans le decor se posent dans le
monde et se materialisent en vrais objets 3D, exactement la ou la
previsualisation les montrait. Aucun asset binaire : tout est construit par
code.

Vingt-cinq courts niveaux d'ilots flottants. Chaque niveau se quitte par un
teleporteur qui exige des piles : on les trouve dans le decor, on les
duplique en posant une photo qui en contient une, ou on les libere des cages.
Certaines photos decoupent au passage les objets lavande pris dans leur
cadre, la molette fait pivoter la photo tenue, viser le sol transforme le
fond d'une photo en plancher, et a partir du niveau 16 un appareil photo
permet de photographier soi-meme le monde lavande (la capture est une copie,
et les barreaux ne l'arretent pas).

Le cadrage produit : `docs/PRD.md` (vision, mecanique detaillee, contrats de
module, plan de test, evolutions reservees dont l'appareil photo) et
`docs/LEVELS_V2.md` (design des niveaux 6 a 15 et budget cinematique).

## Lancer

```
godot --path games/viewpoint
```

ou `run.bat` sous Windows (Godot 4.7+ dans le PATH).

## Controles

| Entree | Action |
|--------|--------|
| ZQSD / WASD (touches physiques) | Se deplacer |
| Souris | Regarder |
| Espace | Sauter |
| Maj | Courir |
| E | Interagir (photo, pile, teleporteur) |
| Clic gauche | Poser la photo tenue (appareil a l'oeil : declencher) |
| Clic droit | Lever / baisser la photo tenue (l'image en grand), ou l'appareil photo mains vides (cadre de visee) |
| Molette | Pivoter la photo tenue (90 degres) |
| F | Reposer la photo tenue |
| R (maintenu) | Rembobiner le temps (une chute dans le vide, elle, recommence le niveau) |
| F11 | Plein ecran |
| Echap | Menu / reprendre |
| Entree | Commencer au niveau 1 / rejouer |

Le menu (titre, pause, victoire) propose une grille de selection des
vingt-cinq niveaux : un niveau atteint reste debloque d'une session a l'autre
(progression dans `user://progress.cfg`).

## Tests

```
godot --headless --path games/viewpoint --script res://tests/run_tests.gd
godot --headless --path games/viewpoint -- --smoke
godot --headless --path games/viewpoint --script res://tools/design_audit.gd
```

La premiere commande couvre les modules purs (geometrie du frustum, catalogue
de photos, niveaux, palette, materiaux, progression). La seconde sonde le vrai
jeu : ramasser, poser, dupliquer, effacer, photographier, rembobiner,
teleporter, puis construire les vingt-cinq niveaux. La troisieme est l'audit
de level design : elle ne demande pas si la donnee est bien formee mais si le
niveau se termine avec les outils qu'il donne.
