# VIEWPOINT (Unity)

Reecriture en Unity du puzzle FPS `games/viewpoint` (Godot 4). Le meme jeu :
memes regles, memes nombres, memes vingt-cinq niveaux, memes textes. Seul le
moteur change.

Les photos trouvees dans le decor se posent dans le monde et s'y materialisent
en vrais objets 3D, exactement la ou l'image les montrait. Poser une photo
REMPLACE tout ce qui entre dans sa perspective : une photo vide de ciel perce
les murs, les sols et les cages. A partir du niveau 16, un appareil photo permet
de photographier soi-meme le monde. Les trois dernieres lecons du jeu sont des
refus : l'acier qu'aucune pose n'ouvre, le plomb qu'aucune pellicule n'imprime,
et la gravite qui fait tomber une caisse posee.

Aucun asset binaire : geometrie, materiaux, textures, ciel, police et vignettes
sont generes par code.

- `docs/PRD.md` : le contrat. Extrait du code Godot et de ses tests, pas des
  anciens documents. C'est lui qui fait foi, section par section.
- `docs/data/photos.json` et `docs/data/levels.json` : le catalogue et les
  niveaux, exportes tels quels depuis la source Godot, en **espace design**
  (x droite, y haut, -z devant). `Assets/Resources/Data/` en est une copie que
  les tests verifient octet par octet.

## Lancer

Ouvrir le projet dans Unity 6.3 LTS (`6000.3.23f1`) et jouer la scene
`Assets/Scenes/Main.unity`, ou en ligne de commande :

```
unity run games/viewpoint_unity
```

La scene ne contient qu'un seul objet : `Main` construit tout le reste au
demarrage, comme la scene squelette de l'original. Pour la regenerer :
menu `VIEWPOINT > Rebuild Main Scene`.

## Controles

| Entree | Action |
|--------|--------|
| ZQSD / WASD (touches physiques) | Se deplacer |
| Souris | Regarder |
| Espace | Sauter |
| Maj | Courir |
| E | Interagir (photo, pile, appareil, teleporteur), portee 1,7 m ; sans cible avec une pile portee : la reposer devant soi |
| Clic gauche | Poser la photo tenue ; mains vides, appareil a l'oeil : declencher |
| Clic droit | Lever / baisser la photo tenue ; mains vides avec de la pellicule : viser |
| Molette | Pivoter la photo tenue (90 degres, sens horaire a l'ecran) |
| F | Reposer la photo tenue |
| R (maintenu) | Rembobiner le temps |
| F11 | Plein ecran |
| Echap | Menu / reprendre |
| Entree | Commencer au niveau 1 / rejouer |

Le menu (titre, pause, victoire) propose une grille des vingt-cinq niveaux : un
niveau atteint reste debloque d'une session a l'autre.

## Tests

```
./verify.sh              # tout, dans l'ordre qui echoue le plus vite
./verify.sh compile      # les scripts compilent
./verify.sh edit         # suites unitaires (EditMode)
./verify.sh play         # sonde d'integration (PlayMode)
./verify.sh audit        # audit de level design
```

Etat au 2026-09-04 : **101 tests EditMode, 29 tests PlayMode, 0 defaut de
level design sur 25 niveaux.**

- Les **suites EditMode** couvrent les modules purs : geometrie du frustum,
  catalogue de photos, capture, decoupage (`Decompose`), progression,
  rembobinage, palette, materiaux, invariants des niveaux, et la conversion
  d'espace propre au portage.
- La **sonde PlayMode** rejoue les vingt-quatre etapes de la sonde d'origine
  dans le vrai jeu : elle *mesure* ce qui se passe (rayons, hauteurs atteintes,
  positions apres chute) au lieu de l'affirmer. C'est elle qui prouve que la
  passerelle enjambe le vide a la bonne hauteur, que la porte se traverse a
  pied, que deux caisses s'empilent a 2,60 m, que le cliche d'une planche la
  reproduit a moins d'un centimetre, que l'acier resiste a une pose mais pas a
  l'objectif, et que le rembobinage rend une cage cassee.
- L'**audit** ne demande pas si la donnee est bien formee mais si un joueur au
  spawn, avec les outils que le niveau lui donne, atteint tout ce qu'on lui
  demande sans jamais s'enfermer.

Deux regles de ce harnais, ecrites parce qu'elles ont ete violees :

- **lire le rapport, jamais le code de sortie seul** : un run a zero test sort 0
  et ressemble exactement a un succes. `verify.sh` refuse un run vide.
- **attendre des pas de PHYSIQUE, jamais des images** : la gravite avance sur le
  pas fixe, et un run headless rend les images bien plus vite que le temps reel.

## Ce que le portage a coute

Les pieges qui ont demande du travail, pour qui reprendra ce code :

- **Un seul miroir sur z.** Toute la donnee reste dans la convention Godot ;
  `DesignSpace.ToUnity` est le seul endroit ou elle devient du +z Unity, et il
  s'applique exactement une fois, la ou une position est posee. Sous un miroir,
  **tous les signes de rotation s'inversent** : le code porte le comportement a
  l'ecran, jamais un signe recopie.
- **Les groupes tiennent a l'activation.** Le `free()` de Godot est immediat, le
  `Destroy` d'Unity est differe a la fin de l'image, `OnDisable` avec lui. Les
  composants s'inscrivent dans `OnEnable` et sortent dans `OnDisable`, et le
  demontage d'un niveau utilise `DestroyImmediate` puis `Groups.Clear()` :
  sinon `LevelBuilder` travaille avec tous les groupes encore pleins du niveau
  qu'on vient de quitter.
- **Rien n'est detruit pendant un niveau.** `Rewind.Retire` sort le noeud vers
  un cimetiere inactif : il quitte tous les groupes et la physique comme une
  liberation, mais reste entier, donc defaire c'est le remettre.
- **Aucune police n'est livree**, donc aucun texte ne s'affichait. TextMeshPro
  ne trouve une police que si quelqu'un a importe TMP Essential Resources, ce
  qui depose un atlas binaire dans `Assets`. `Fonts.cs` en genere une au
  demarrage a partir d'une police systeme, en atlas dynamique.
- **Le carre du viseur et celui de l'image levee sont le meme**, derive de
  `PhotoMath.PhotoFovDeg` et `PlayerController.CameraFov`. Ecrire le 0,6077 qui
  en resulte laisserait les deux deriver l'un de l'autre, et c'est toute la
  promesse du jeu qui se joue la.
- **Le tonemapping est Neutral, pas ACES** : ACES desature les albedos clairs,
  c'est-a-dire exactement de quoi cette palette pastel est faite.

## Parite avec l'original

| harnais | Godot | Unity |
|---------|-------|-------|
| suites unitaires | 1241 verifications | 101 tests |
| sonde d'integration | 396 verifications | 29 tests (24 etapes) |
| audit de level design | 0 defaut / 25 niveaux | 0 defaut / 25 niveaux |

Les comptes ne se comparent pas directement : une verification Godot est une
assertion, un test NUnit en regroupe plusieurs. Ce qui se compare, ce sont les
comportements couverts, listes section 17 du PRD.
