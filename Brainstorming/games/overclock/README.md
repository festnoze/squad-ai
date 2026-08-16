# OVERCLOCK

Un entrepot automatise, un drone, et aucune commande directe. Vous n avez pas de
manette : vous avez un panneau de programmation. On glisse des instructions dans
des slots, on appuie sur EXECUTER, et on regarde la machine faire exactement ce
qu on lui a ecrit, l instruction courante surlignee au fur et a mesure. Le
nombre de slots est volontairement ridicule, alors pour couvrir une zone entiere
il faut des procedures qui s appellent elles memes (c est la boucle), des
conditions de couleur (c est le branchement), et de la peinture au sol (c est la
memoire). Objectif d une zone : allumer toutes les cibles.

## Commandes

| Touche | Effet |
|---|---|
| `Entree` ou EXECUTER | Lancer le programme |
| `Echap` | Arreter le run, sinon ouvrir la pause |
| `F10` ou PAS A PAS | Executer une seule instruction |
| `Ctrl` + `Z` | Annuler une edition (illimite) |
| `R` | Effacer tout le programme |
| `1` a `9` | Poser l instruction correspondante de la palette |
| `Fleches` | Naviguer entre les slots |
| `C` | Faire tourner la condition de couleur du slot |
| `Suppr` | Vider le slot |
| Souris | Glisser une instruction, orbiter la camera, molette pour zoomer |
| Clic droit sur un slot | Vider le slot |

Un clic sur un slot deja rempli fait tourner sa condition de couleur.

## Jeu d instructions

| Instruction | Regle exacte |
|---|---|
| AVANCER | Une case devant, uniquement si elle est a la **meme hauteur** |
| GAUCHE / DROITE | Quart de tour |
| SAUT | Monte d **une** marche, descend de n importe quelle hauteur, ou franchit un vide d **une** case si la case d apres est a la meme hauteur |
| ACTIVER | Allume la cible sous le drone |
| PRENDRE / POSER | Saisit ou depose la caisse **devant** ; une caisse lachee dans un vide le comble |
| PEINDRE | Peint la dalle sous le drone en rouge, vert ou bleu |
| PRINCIPAL / P1 / P2 | Appelle une procedure, y compris celle en cours |

Chaque instruction peut porter une **condition de couleur** : elle est ignoree
si la dalle sous le drone n est pas de cette couleur. Une instruction refusee
(mur, denivele, rien a prendre) ne casse pas le programme : le drone se cogne,
la raison s affiche, et l execution continue. La difficulte vient de la
reflexion, jamais de la punition.

Garde fous : pile d appels bornee a 200, compteur d instructions executees borne
a 5000. Au dela, le run s arrete proprement sur "boucle infinie detectee" et le
panneau montre ou. Un appel place dans le dernier slot **utile** d une procedure
(les slots vides qui suivent ne comptent pas) est un appel terminal : il remplace
sa frame au lieu d en empiler une, donc une boucle recursive peut tourner
indefiniment sans saturer la pile. Une recursion qui a encore du travail apres
l appel, elle, empile bel et bien.

## Score

Le score est le nombre d instructions **posees**, pas executees. Or si le
programme tient dans l optimum du niveau, argent a +2, bronze a +4. C est ce qui
pousse a remplacer une longue sequence par une recursion.

## Progression

Quatorze zones. Les trois premieres enseignent une mecanique chacune : la
sequence, la procedure qui s appelle elle meme, la condition de couleur. Ensuite
viennent les sous programmes, le relief et le saut, la peinture comme memoire,
les caisses, puis des combinaisons. La progression et les meilleurs scores sont
sauvegardes en `localStorage` sous le prefixe `overclock.`, ainsi que le
programme en cours de chaque niveau.

## Notes techniques

- **Zero build** : ES modules natifs, aucune dependance a installer. Deposer le
  dossier dans `games/` suffit, la console arcade le detecte.
- **three.js r169** vendorise dans `vendor/three.module.js`, resolu par
  l importmap de `index.html`. Aucun addon `three/examples/jsm/*`.
- **Zero asset binaire** : toutes les textures sont dessinees dans un canvas 2D
  avec un PRNG graine, tous les sons sont synthetises en Web Audio, toute la
  geometrie est generee en code.
- Le panneau de programmation est du **DOM par dessus le canvas** : c est la
  seule facon d avoir un glisser deposer et un texte nets a toute resolution.
- L interprete (`src/vm.js`) ne connait ni three ni le DOM. Il consomme un slot
  par appel a `step()` et rend un evenement, ce qui permet x0.5, x4 et le pas a
  pas sans une ligne de code specifique.
- Rendu : trois `InstancedMesh` pour tout l entrepot, une lumiere directionnelle
  avec ombres douces, halo ventral simule par un disque additif. Une trentaine
  de draw calls.

## Lancer

Par la console arcade du depot :

```
python games/arcade/arcade.py
```

puis choisir OVERCLOCK. Tout chemin est relatif, le jeu fonctionne servi sous
`/g/overclock/`.
