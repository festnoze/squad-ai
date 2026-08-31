# VIEWPOINT

Puzzle game 3D a la premiere personne en Godot 4, inspire de la mecanique
centrale de Viewfinder : les photos trouvees dans le decor se posent dans le
monde et se materialisent en vrais objets 3D, exactement la ou la
previsualisation les montrait. Aucun asset binaire : tout est construit par
code.

Quinze courts niveaux d'ilots flottants. Chaque niveau se quitte par un
teleporteur qui exige des piles : on les trouve dans le decor, on les
duplique en posant une photo qui en contient une, ou on les libere des cages.
Certaines photos effacent au passage les objets lavande pris dans leur cadre,
la molette fait pivoter la photo tenue, et viser le sol transforme le fond
d'une photo en plancher.

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
| Clic gauche | Poser la photo tenue |
| Molette | Pivoter la photo tenue (90 degres) |
| Clic droit | Reposer la photo tenue |
| R | Recommencer le niveau |
| F11 | Plein ecran |
| Echap | Menu / reprendre |
| Entree | Commencer au niveau 1 / rejouer |

Le menu (titre, pause, victoire) propose une grille de selection des quinze
niveaux : un niveau atteint reste debloque d'une session a l'autre
(progression dans `user://progress.cfg`).

## Tests

```
godot --headless --path games/viewpoint --script res://tests/run_tests.gd
godot --headless --path games/viewpoint -- --smoke
```

La premiere commande couvre les modules purs (geometrie du frustum, catalogue
de photos, niveaux, palette, materiaux, progression). La seconde sonde le vrai
jeu : ramasser, poser, dupliquer, effacer, teleporter, construire les cinq
niveaux.
