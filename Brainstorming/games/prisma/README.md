# PRISMA

Puzzle optique en 3D. Une chambre, un emetteur qui crache un faisceau blanc, et des cibles qui refusent de s allumer tant qu elles ne recoivent pas exactement la couleur qu elles attendent. Vous posez des miroirs, des prismes, des filtres, des splitters et des combinateurs sur la grille : le faisceau se recalcule instantanement a chaque geste, sans bouton de tir. Quatorze chambres, aucune contrainte de temps, aucune punition, un nombre d annulations illimite. La difficulte vient uniquement de la reflexion.

## Lancer

Le jeu est servi par la console arcade du depot :

```
python games/arcade/arcade.py
```

puis choisir PRISMA. Zero build, zero dependance : ES modules natifs et three.js r169 vendorise dans `vendor/`.

## Commandes

| Touche | Effet |
|---|---|
| Clic gauche | Poser le composant selectionne, ou selectionner un composant deja pose |
| Clic droit / Espace | Tourner le composant vise (ou l orientation du prochain a poser) |
| Molette | Tourner si un composant est vise, sinon zoomer |
| 1 a 5 | Choisir miroir, prisme, filtre, combinateur, splitter |
| Suppr / Clic milieu | Retirer le composant vise |
| Ctrl+Z | Annuler (illimite) |
| R | Recommencer la chambre |
| Souris glissee | Orbiter |
| C | Recadrer la camera |
| H | Reafficher la regle de la chambre |
| M | Couper le son |
| Echap | Pause |

## Regles de simulation

Le faisceau avance case par case dans les quatre directions cardinales. Chaque segment porte un masque RGB (trois bits) et une intensite.

- **Miroir** : devie a 90 degres, mais **une seule face reflechit**. Un miroir dont l orientation est r ouvre les faces r et r+1 ; un faisceau qui arrive par le dos est absorbe. Quatre orientations reellement distinctes.
- **Prisme** : separe le faisceau en trois, a gauche, tout droit et a droite. Les trois rotations font tourner l affectation des couleurs (les billes posees sur le prisme indiquent laquelle). Une composante absente du faisceau entrant ne produit pas de sortie.
- **Filtre** : ne garde qu une composante (rouge, vert ou bleu). Direction inchangee.
- **Combinateur** : additionne tout ce qui entre et ressort par sa fleche. Un faisceau qui entre par la face de sortie est absorbe.
- **Splitter** : moitie tout droit, moitie a 90 degres, selon le meme modele de faces que le miroir. Par le dos, c est du verre : le faisceau passe.
- **Portails** : teleportent le faisceau vers leur jumeau en conservant sa direction.
- **Cible** : allumee par **un seul** faisceau de la couleur exacte. Deux faisceaux de couleurs differentes ne s additionnent pas sur une cible : c est precisement pour cela que le combinateur existe.

Deux filets de securite obligatoires dans `src/beam.js` : une table de visite indexee par (case, direction, couleur) coupe toute boucle de miroirs des sa premiere repetition, et un budget dur de 2400 segments arrete les cascades de splitters.

Les combinateurs recoivent un faisceau qui n existe pas encore quand on les atteint la premiere fois. La propagation est donc rejouee jusqu a ce que l ensemble des entrees des combinateurs cesse de grandir. Ces entrees ne peuvent que gagner des bits, donc l iteration converge toujours (en deux ou trois passes en pratique).

## Score

Le score d une chambre est le nombre de composants poses, compare a l optimum connu, defini dans les donnees du niveau : or si egal ou inferieur, argent a +1, bronze a +2. La progression (derniere chambre atteinte et meilleur score par chambre) est conservee dans `localStorage` sous les cles prefixees `prisma.`.

## Notes techniques

- **Zero asset binaire.** Toutes les textures sont dessinees dans un canvas 2D au demarrage (sol, panneaux, halo, cibles, portails, sonde d environnement equirectangulaire, icones de l inventaire en data URL). Tous les sons sont synthetises en Web Audio. Toute la geometrie est generee en code.
- **Rendu du faisceau.** Deux `InstancedMesh` (un coeur emissif fin et un halo additif large) dessinent la totalite des segments en deux appels, quelle que soit la complexite du trajet.
- **Poussiere.** Un seul nuage de `Points` dont le vertex shader echantillonne une texture minuscule a la taille du plateau, remplie a chaque resolution avec la couleur du faisceau par case. Les motes s allument donc exactement la ou un faisceau passe, sans que le CPU touche une seule particule.
- **Metal dans le noir.** Les miroirs sont metalliques : la scene fabrique un PMREM a partir de la sonde d environnement dessinee au canvas, sinon un materiau metallique sans environnement rend noir mat (piege connu de ce depot).
- `logarithmicDepthBuffer` n est pas active, les `ShaderMaterial` custom n ont donc pas besoin des chunks `logdepthbuf_*`.
- Le fond de scene n est jamais noir pur (violet tres sombre) et le brouillard exponentiel utilise la meme teinte.

## Verification des niveaux

Les quatorze chambres portent chacune leur solution de reference dans `src/levels.js`. Un script de verification (hors depot, dans le scratchpad) rejoue chaque solution dans le vrai solveur pour prouver que le niveau est resolvable, que l optimum annonce correspond bien a une disposition qui marche, qu aucune piece ne se recouvre, que le budget de segments n est jamais sature, et qu aucune solution plus courte n existe dans les trois premieres profondeurs de recherche.
