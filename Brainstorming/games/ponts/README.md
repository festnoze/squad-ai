# PONTS DE FORTUNE

Un ravin, un budget serre, quatre materiaux. Vous dessinez la structure dans le plan
vertical du pont, puis vous lancez le convoi et vous regardez la physique trancher. Les
membres se colorent en direct selon ce qu ils encaissent: bleu en compression, rouge en
traction, et la couleur sature a mesure que l on approche de la rupture. Quand le pont
cede, l effondrement est rejoue au ralenti, camera braquee sur le premier element qui a
lache, puis le chantier revient intact: la difficulte vient de la reflexion, jamais de la
punition. Quatorze chantiers, des portees de douze a cinquante-deux metres, des piliers,
des pylones, un tunnel et des convois de plus en plus lourds.

## Commandes

| Touche | Effet |
|---|---|
| Clic gauche glisse | Tracer un element entre deux noeuds de la grille |
| `1` `2` `3` `4` | Bois, acier, cable, route |
| Clic droit | Retirer l element sous le curseur (rembourse) |
| Clic droit glisse | Pivoter la camera |
| Clic milieu glisse | Deplacer la vue |
| Molette | Zoom |
| `Ctrl` + `Z` | Annuler, sans limite |
| `Espace` | Lancer le convoi / revenir au chantier |
| `R` | Tout effacer |
| `V` | Revenir a la vue de cote |
| `C` | Camera libre ou suivi du convoi |
| `M` | Couper le son |
| `Echap` | Pause |

## Regles

- **Bois**: bon marche, casse vite, et perd encore de la capacite en compression quand
  la piece est longue (flambage).
- **Acier**: quatre fois plus resistant, trois fois plus cher.
- **Cable**: presque gratuit mais ne travaille **qu en traction**. En compression il
  devient simplement mou et ne pousse rien du tout. C est ce qui rend une suspension
  possible la ou un treillis coute trop cher.
- **Route**: obligatoire pour que le convoi roule. Elle se pose uniquement au niveau du
  tablier, entre deux cases voisines, et c est la piece la plus fragile: elle doit etre
  portee, pas se porter elle meme.
- Les ancrages sur les falaises, les piliers de pierre et les pylones sont fixes et
  gratuits.
- Une seule piece par paire de noeuds, quel que soit le materiau: doubler une poutre par
  un cable sur le meme segment est refuse ("deja construit ici"). Pour renforcer une
  travee, il faut passer par un autre chemin (triangle, chandelle, suspente).
- Reussite quand tous les vehicules atteignent l autre rive. Le score retient les credits
  restants et la charge maximale supportee.

## Notes techniques

- Zero build, zero dependance: modules ES natifs, `three.js` r169 vendorise dans
  `vendor/`, importmap dans `index.html`. Aucun addon `three/examples/jsm/*`.
- Zero asset binaire: toutes les textures sont peintes dans un `<canvas>` 2D, tous les
  sons sont synthetises en Web Audio, toute la geometrie est generee en code.
- Solveur maison (`src/physics.js`), pur JavaScript sans three.js, donc testable depuis
  node: verlet a pas fixe de 1/120 s avec accumulateur, vingt passes de relaxation des
  contraintes de distance. La force reelle dans un membre est recuperee depuis
  l impulsion de contrainte (`e * raideur / (wa + wb)` accumule, divise par `dt^2`), ce
  qui donne des newtons comparables a une capacite par materiau: c est ce nombre qui
  colore les pieces et qui les casse.
- Le plan dessine en 2D est **gonfle en 3D**: chaque element devient deux membres
  paralleles ecartes de la largeur de la chaussee, plus des traverses et des croix de
  contreventement. Le pont a donc une vraie epaisseur et peut ceder de travers.
- Le convoi avance en coordonnee de colonne continue et non en X monde: quand le tablier
  s allonge ou s effondre, X cesse d etre monotone et un vehicule pilote en X traverserait
  les trous.
- Une position non finie ne fait pas planter la simulation: le noeud est restaure a sa
  derniere position saine et les elements qu il tenait sont rompus.
- Le rejeu lit exactement le meme tampon d etat que le rendu temps reel, d ou un ralenti
  identique au direct.
- Progression et meilleurs ponts en `localStorage`, prefixe `ponts.`.

## Lancement

Le jeu est servi par la console arcade du depot:

```
python games/arcade/arcade.py
```

puis choisir PONTS DE FORTUNE. Aucun chemin absolu n est utilise, le dossier fonctionne
sous n importe quel prefixe d URL.
