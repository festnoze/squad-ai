# VIEWPOINT v2 - Design des niveaux 6 a 15

Document de design. Version 1.0, 2026-08-31. Complement du PRD (section 11).
Regles d'ecriture du projet : texte joueur en francais, code en anglais,
jamais de tiret cadratin.

---

## 1. Nouvelles mecaniques

### 1.1 Rotation de la photo (molette)

La photo tenue pivote par pas de 90 degres **autour de l'axe de visee**
(roulis). Implementation : le roulis est applique au PhotoPlacer lui-meme,
donc le fantome ET l'ancre de pose tournent ensemble ; l'egalite fantome =
solide (PRD 3.2) est preservee par construction.

> v4 : le fantome 3D a disparu (section 1.7). Le roulis reste applique au
> placer ; on le lit sur l'image 2D levee, plus dans le monde.

Consequence geometrique a assumer dans le design : une boite plate tournee de
90 degres devient un panneau vertical (une « tranche »). Les casse-tetes de
rotation utilisent donc surtout le **retournement a 180 degres**, qui garde
les plateaux horizontaux mais **inverse leur decalage** dans le cadre :

- une dalle decentree vers le bas passe en hauteur ;
- une dalle decentree a droite passe a gauche.

Les poses a 90 et 270 degres restent legales (panneaux verticaux : parapets,
bouchons) mais aucun niveau ne les exige.

### 1.2 Cages et enclos

Nouvel element de niveau (`cages` dans LevelDefs) : barreaux visuels,
collision pleine (le rayon d'interaction ne passe pas entre les barreaux),
avec deux variantes lisibles par la couleur :

- **lavande emissive = effacable** : toute photo dont le frustum attrape le
  centre de la cage la supprime (meme groupe `erasable` que les caisses) ;
- **sombre = permanente** : on n'efface pas, on contourne (par dessus si elle
  n'a pas de toit).

Options par cage : `roof` (toit ou enclos ouvert), `erasable`.

> v4 : la distinction lavande/sombre est devenue un indice de lore purement
> visuel. TOUTE cage est cassable par n'importe quelle pose qui attrape son
> centre (section 1.7) ; le corps des cages vit dans le groupe "breakable".

### 1.3 Photo dans la photo

Nouveau genre de prop `photo` : a la pose, il materialise un **objet photo
ramassable** (le meme PhotoItem que ceux places par le niveau). Chaine de
materialisation : poser A fait apparaitre la photo B, qu'on pose a son tour.
Le test de solvabilite compte les piles **recursivement** a travers ces
imbrications (garde anti-cycle).

### 1.4 Tangage assume (poser vers le bas / vers le haut)

Deja permis par l'ancre camera complete : viser vers le bas incline la
passerelle en plan descendant, et le **backdrop d'une photo posee en regardant
le sol devient un plancher** (quad perpendiculaire a la visee).

> **v6.1 : LA RAMPE DE CIEL EST MORTE, et il faut le dire net.** Le fond peint
> est perpendiculaire a la visee, donc sa pente vaut 90 degres moins l'angle de
> visee : il faut viser a 45 degres AU MOINS pour qu'on puisse y marcher
> (floor_max_angle vaut 45). Or son bord bas vaut
> `1.62 + profondeur x (sin angle - tan25 x cos angle)`, soit 10.73 m a 45
> degres avec un fond a 24 m, quand un escalier plus un saut plafonne a 6.13.
> Fermer l'angle baisse la rampe mais la rend trop raide : les deux contraintes
> se contredisent, il n'existe aucun angle qui marche.
>
> Le niveau 13 etait entierement bati dessus. Il a ete rebati sur la DOUBLE
> VOLEE (section 2), qui n'exigeait aucun code nouveau et qu'aucun niveau
> n'exploitait. Le plancher vise vers le bas, lui, existe toujours, mais a 24 m
> il tombe sous le kill_y de tous les niveaux : ne comptez plus dessus.

> Et une verite geometrique a ne pas oublier en concevant : **une pose piquee
> porte MOINS loin qu'une pose a plat**, et tomber ne coute rien dans ce jeu.
> Aucun plongeon ne peut donc etre rendu obligatoire. Le niveau 10 le promettait
> dans son sous-titre, il ne le promet plus.

### 1.5 Decoupage partiel et regle du scelle

Les blocs effacables ne disparaissent plus en bloc : la partie de leur volume
prise dans le frustum est decoupee (boite moins boite, 6 fragments au plus,
eux-memes effacables). Deux consequences de design :

- **Regle du scelle** : une photo qui contient un mur pleine trame (la porte)
  ne decoupe que **jusqu'au plan de ce mur**, et le mur remplit exactement la
  section du frustum a cette profondeur. Le trou creuse devant est donc
  referme par le contenu : aucun interstice. Corollaire joueur : la porte ne
  decoupe qu'a moins de 7.4 m, il faut s'approcher. Un test unitaire
  (test_porte_seal) et un rayon de la sonde verrouillent cette regle.

  > v6.1 : le fond peint ne scelle plus rien, il est parti trois fois plus
  > loin (section 1.7). Seules les photos a mur plein, comme la porte, sont
  > encore scellees, et ce sont les seules qui en avaient besoin.
- **Le langage du sol (v5.5)** : le sol GRIS est permanent, une photo posee
  par dessus lui est ajoutee (poser un pont ajoute un pont, ca ne creuse
  rien) ; le sol PALE, teinte claire du lavande, se decoupe comme un mur.
  C'est le seul sol qu'un cadre peut emporter. Outil au niveau 11, jamais un
  piege : ce qui va disparaitre se voit avant d'appuyer.

### 1.6 R : le filet anti-blocage

Les photos sont consommables, un niveau complexe peut donc etre gaspille. Il
faut donc un recours, et c'est R.

> Corrige en v6 : cette section decrivait R comme un rechargement de niveau,
> ce qu'il n'est plus depuis la v5. R MAINTENU rembobine (PRD section 12) :
> la pose ratee est defaite, la photo revient en main, les piles reviennent au
> sol. C'est un meilleur filet qu'un rechargement, mais il a une limite qui
> compte pour le design : l'historique plafonne a cinq minutes. Une photo
> gaspillee dont on ne s'apercoit qu'apres est definitivement perdue, et il ne
> reste alors que le menu (Echap) ou une chute volontaire pour repartir.
>
> Consequence a tenir dans les niveaux : un niveau qui ne donne QU'UNE photo
> et dont la pose correcte demande un placement precis est un piege silencieux
> pour qui n'a pas compris le rembobinage. On lui laisse une photo de marge.

### 1.7 v4 : le remplacement total, la photo vide, la physique

La v4 (SPEC_V4.md) change la nature de la pose : une photo est la
representation 2D d'un espace 3D complet, et la poser REMPLACE tout ce qui
entre dans sa perspective, jusqu'a la distance de son fond.

**Remplacement total.** La decoupe ne s'arrete plus aux blocs lavande : tout
bloc-boite (plateformes, decors, contenus deja poses) est decoupable. La
decoupe va jusqu'a `backdrop.depth`, et le fond 2D peint de la photo (devenu
un bloc mince, lui-meme decoupable) est plante a cette profondeur :

> **v6.1 : le fond peint a recule d'un facteur 3.** Il se plantait au plan
> d'effacement, donc au bout du contenu : une passerelle de 8 m posait un mur
> plein a 9.5 m, et traverser un gouffre revenait a marcher dans le ciel.
> C'est le defaut que cinq revues de niveau sur cinq ont fini par trouver, et
> qu'un joueur a signale au niveau 5. Le fond est desormais le LOINTAIN de
> l'image, pas son couvercle. La decoupe, elle, n'a pas bouge.

| photo | decoupe jusqu'a | fond peint a | largeur du fond |
|---|---|---|---|
| passerelle | 9.5 m | 28.5 m | 26.6 m |
| pile | 8.0 m | 24.0 m | 22.4 m |
| escalier | 9.0 m | 27.0 m | 25.2 m |
| porte | 7.4 m | aucun, scellee par son mur a 6.0 m | |
| console, corniche, coffret | 6.0 m | 18.0 m | 16.8 m |
| caisse | 5.0 m | 15.0 m | 14.0 m |
| cliche (appareil) | 12.0 m | 36.0 m | 33.6 m |

Ce que le decouplage coute, et qu'il faut assumer : une decoupe n'est plus
refermee par le fond. Un trou perce dans un mur lavande reste ouvert. Ce n'est
pas une regression, c'est le comportement de la photo vide applique partout,
et il ne peut rendre un mur que plus facile a franchir, jamais moins.

Consequences design appliquees a TOUS les niveaux :

- les plateformes d'arrivee des poses obligatoires font 12 m ou plus de
  large : un fond centre laisse des couloirs de contournement de 1.5 m ;
- le teleporteur (indestructible) reste joignable en contournant le fond ;
- regle utile partout : le fond de l'escalier depasse la derniere marche de
  1.2 m et se trouve 0.8 m derriere elle. Un saut (+1.5) passe TOUJOURS par
  dessus le fond d'un escalier qu'on vient de gravir.

**Cages.** Toute cage est cassable des que son centre tombe dans le frustum
d'une pose (profondeur = celle de la photo posee). Les puzzles de cage sont
desormais des puzzles d'economie (quelle photo sacrifier), d'alignement
(deux serrures dans un meme frustum, niveau 9) ou de distance (une cage
cassee ne sert a rien si le gouffre reste, niveau 19).

**La photo vide.** L'appareil consomme toujours une pellicule et retourne
toujours une photo, meme cadree sur le ciel : props vides, fond ciel a 12 m.
La photo vide est l'outil de percage maximal du jeu (12 m de profondeur,
rien de materialise). Le niveau 16 l'exige explicitement.

**Physique.** A la pose, les piles et les boites de 1.6 m ou moins par cote
(marquees "loose" a la capture) deviennent des corps rigides : posees en
l'air ou a l'envers (roll 180), elles TOMBENT. C'est un outil (niveaux 14,
18 et 19). E sans cible repose une pile portee devant soi.

**Portee d'interaction 1.7 m.** Le ramassage a distance a disparu : les
vitrines des niveaux 12 et 15 sont des niches de 1.0 m de profondeur, pile
a 0.5 m de l'ouverture.

**Plus de fantome 3D.** La photo levee s'inspecte en 2D (clic droit, molette
pour la tourner) et le resultat ne se decouvre qu'a la pose. Les poses de
precision ont des dalles-reperes au sol : teal (bleu-vert) pour la route
standard, accent (corail) pour la pose critique du niveau. Le repere marque
le point ou se tenir ; la direction se lit dans la disposition du niveau.

Les niveaux 1 a 5 sont adaptes (plateformes d'arrivee elargies a 12-14 m,
reperes ajoutes, piles deplacees hors des axes de pose) ; les niveaux 6 a 20
sont revises en profondeur (sections 4 et 4 bis).

### 1.8 v6 : la matiere qui dit non

Trois ajouts, et tous les trois sont des REFUS, pas des pouvoirs. Le joueur
a passe vingt niveaux a apprendre ce qu'il peut faire ; les cinq derniers lui
apprennent ce qu'il ne peut pas.

**Acier.** Une cage `"sealed": true` n'est ouverte par aucune pose (elle n'est
pas dans le groupe `breakable`). L'objectif, lui, passe entre les barreaux :
la seule sortie est de photographier ce qu'elle enferme et de materialiser la
copie ailleurs. Une pile sous acier n'est donc **jamais ramassable**, c'est
un modele. Corollaire technique : la pellicule ne copie plus les cages du
tout, sans quoi la copie de la cage se refermerait autour de la copie de la
pile.

**Plomb.** Une pile de `sealed_batteries` vaut une pile au teleporteur mais
aucune pellicule ne l'imprime. Elle le dit a l'oeil : gris de plomb au lieu
d'ambre, et **inerte** quand les autres flottent et tournent. Elle reste
plomb a travers les mains (`Game.carried_sealed`, repose du plomb en
premier), sinon il suffirait de la poser et de la rephotographier.

**Poids et rotation.** Une caisse posee a l'endroit apparait 1 m sous l'oeil
et se pose au sol : sommet 1.30. La meme photo **retournee a 180** apparait
1 m au dessus de l'oeil, 2.6 m devant, et **tombe**. En visant la premiere
caisse, elle retombe dessus : sommet 2.60, soit 4.10 avec un saut. A
l'endroit, on ne depassera jamais 1.30. Les tours des niveaux 23 et 25 sont
taillees exactement sur cet ecart.

| coup | sommet atteint | avec le saut |
|---|---|---|
| une caisse a l'endroit | 1.30 | 2.80 |
| deux caisses, la seconde retournee | 2.60 | 4.10 |

Les objets libres sont des `RigidBody3D`, pas des blocs : aucune pose ne les
decoupe, donc un empilement survit a la photo suivante.

**La pellicule n'imprime pas la pellicule.** Une copie de pile sort plombee,
donc incopiable. Avant ca, une copie etait elle-meme un modele : C piles et F
pellicules donnaient C x 2^F piles, et aucune exigence de teleporteur ne
voulait plus rien dire. Une pellicule rapporte desormais au plus une copie par
pile copiable cadree.

**Les deux nombres qui commandent le design des niveaux :**

| fait | consequence |
|---|---|
| le saut sprinte porte a 7.43 m, le tablier d'une passerelle a 8 m | aucun gouffre PLAT ne peut etre rendu obligatoire ; il faut du denivele |
| l'objectif n'a ni occlusion ni portee autre que 12 m | une montee n'est une montee que si ce qui l'attend en haut est PLOMBE |
| une pose piquee porte MOINS loin qu'une pose a plat, et tomber ne coute rien | aucun plongeon ne peut etre rendu obligatoire ; on peut l'inviter, jamais l'exiger |
| le fond peint est un mur plein a la profondeur de la photo | ce que la pose doit atteindre doit etre DEVANT ce plan, sinon la pose scelle sa propre cible |

Ce dernier point est le defaut le plus frequent trouve par la revue des
niveaux 6 a 20 : cinq bloquants sur six etaient une pile ou une plateforme
sertie derriere le mur de la photo censee y donner acces, ou un contenu
materialise a l'interieur d'un bloc gris. C'est invisible sans connaitre la
direction de visee, d'ou les champs `photo`, `aim` et `roll` que porte
desormais un repere (PRD section 8).

Ces deux lignes ont coute six niveaux revus (1, 5, 7, 10, 17, 20) qui se
bouclaient sans poser une seule photo, ou dont la montee se contournait d'un
cliche pris depuis le sol.

**Correctif livre avec la v6** : le fond peint etait devenu permanent. Il est
de nouveau decoupable, sinon un mur de ciel pose de travers murait une route
sans recours.

## 2. Budget cinematique (les nombres qui font les puzzles)

Mesures moteur (gravite 14, saut 6.5, marche 5, sprint 8), exprimees par
rapport aux pieds du poseur :

| Moyen | Gain vertical | Notes |
|---|---|---|
| Saut | +1.50 | portee horizontale ~4.6 m (7.4 en sprint, tolere comme technique avancee) |
| Caisse (photo) | +1.30 | cube 1.3, sautable |
| Console 0 deg | +1.17 | dalle 2 x 2 a 3 m devant |
| Console 180 deg | +2.37 | inaccessible depuis son point de pose (2.37 > 1.50) : il faut un appui voisin a +0.9 ou plus |
| Corniche 0 deg | +1.17, décalée a droite (+1.6) | franchit une douve laterale |
| Corniche 180 deg | +2.37, décalée a gauche (-1.6) | idem cote oppose et haut |
| Escalier | +4.62 | rampe 33 deg, franchit un mur de 3 m s'il est pris a 6 m ou plus |
| Passerelle | 0 (8 m de portee) | piquee a -40 deg : ~6 m d'avancee pour ~5 m de descente |
| Backdrop (pile) vise au sol | plancher a ~6.3 m sous les pieds | plan 7.4 x 7.4, pente residuelle ~7 deg (limite de tangage 83 deg) |
| ~~Backdrop vise vers le haut~~ | ~~rampe~~ | **Mort en v6.1** : marchable exige de viser a 45 deg ou plus, et le bord bas est alors a 10.7 m, hors d'atteinte. Voir section 1.4. |
| Deux volees d'escalier | +10.75 | la seconde se pose depuis le palier de la premiere : 4.62 deux fois, plus le saut. Sujet du niveau 13. |
| Porte (scelle) | mur 5.6 x 5.6 a 6 m, ouverture 1.6 x 2.6 | ne decoupe que jusqu'a 6.2 m ; le mur rebouche tout ce qui est decoupe |

Regle d'or issue du tableau : **une console 180 seule ne se monte pas**. Tout
puzzle qui l'exige doit fournir l'appui intermediaire (caisse, bloc du decor,
console 0).

## 3. Nouvelles photos au catalogue

| Id | Contenu | Role |
|---|---|---|
| console | dalle 2 x 2 decentree bas (-0.6) | marchepied (0 deg) ou plateforme haute (180 deg) |
| corniche | dalle 1.8 x 1.8 decentree bas-droite (+1.6, -0.6) | choisir le cote : droite-bas ou gauche-haut |
| caisse | cube 1.3 pose au sol | appui, rehausse, complement d'escalier |
| coffret | socle + **photo « pile »** | chaine de materialisation, duplication indirecte |

## 4. Les niveaux 6 a 15 (revises v4)

Chaque entree : intention, disposition, solution attendue, rattrapage.

### 6. La cage (2 piles) - toute pose fauche une cage
Plateau simple, une cage lavande a toit qui contient LES DEUX piles du
niveau, une seule photo (porte). La lecon v4 : n'importe quelle pose dont le
frustum attrape le centre de la cage la detruit entierement, meme une porte.
Le repere corail est a 5.2 m du centre de la cage : sous la profondeur de
remplacement de la porte (6.2 m).
Rattrapage : R si la porte est posee ailleurs.

### 7. Pivot (2 piles) - la rotation, sans fantome
Deux perchoirs (2.2 a droite, 3.0 a gauche) de part et d'autre d'une douve
de 2 m, deux corniches, deux reperes au sol. Corniche 0 deg depuis le repere
teal (dalle a droite, +1.17) pour le perchoir droit ; corniche 180 depuis le
repere corail (dalle a gauche, +2.37), abordee via le bloc de pierre (1.5),
pour le gauche. v4 : la pose ENTAILLE le perchoir (tout se decoupe) ; la
dalle se pose dans l'entaille et sert de marche vers le sommet restant. Les
piles sont aux coins opposes des perchoirs, a plus de 6 m des reperes : hors
de la profondeur de remplacement d'une corniche posee au bon endroit.
Rattrapage : R si une corniche part du mauvais cote.

### 8. Le coffret (2 piles) - la photo dans la photo
Une pile libre ; la photo coffret materialise un socle et la photo « pile ».
v4 : poser depuis le repere teal, dos au centre, pour que le fond peint du
coffret (6 m) tombe au dela du bord du plateau. La pile dupliquee est un
corps rigide : elle tombe au sol et se ramasse a 1.7 m.

### 9. L'enclos (3 piles) - l'economie : une pose, deux serrures
Trois photos, trois verrous : pile A dans une cage sombre A TOIT (une pose
la casse), pile B sur un perchoir a 3.3 (caisse +1.3, puis console 180 a
+2.37, saut), pile C au sommet d'une tour a 4.0 (escalier). Le compte est
juste : aucune photo n'est dediee a la cage. La solution est l'ALIGNEMENT,
depuis le repere corail : le centre de la cage (a 6 m) et la tour (a 13 m)
sont sur le meme axe ; UNE pose d'escalier casse la cage ET dresse la volee
vers la tour. En haut, sauter par dessus le fond peint de l'escalier (regle
du 1.2 m, section 1.7) pour atteindre le sommet.
Rattrapage : R si l'escalier part sans prendre la cage dans le cadre.

### 10. Plongeon (2 piles) - poser en piquant vers le bas
Ilot bas 5 m sous le plateau de depart, 5.5 m en avant, hors de portee de
saut. Passerelle piquee a ~40 deg depuis le repere corail au bord : plan
incline qui descend jusqu'a l'ilot. v4 : le fond peint de la passerelle
(8.9 m de large) arrive incline en travers de l'ilot ; l'ilot fait 12 m de
large et se contourne par les flancs, le teleporteur est decale a l'est.
Rattrapage : passerelle posee a plat = pont vers rien, R.

### 11. Sous le pont (2 piles) - l'ordre des poses
Structure inchangee : pont de sol lavande entre deux iles, etagere etroite
4 m sous lui, tourelle sur l'ile d'en face. v4 generalise la lecon : TOUT
sol se decoupe, plus seulement le lavande. Ordre impose : traverser le pont,
prendre la pile de la tourelle (console 0 deg + saut), percer le pont depuis
le repere corail de l'ile d'en face (console restante), tomber par le trou
sur l'etagere, pile 2, puis remonter par l'escalier pose depuis le repere
teal de l'etagere. La sortie de la volee saute par dessus son fond peint et
retombe sur les bords intacts de l'ile (le milieu a ete decoupe par la pose).
Danger enseigne : poser face au pont AVANT de l'avoir traverse coupe la
route (R).

### 12. La vitrine (4 piles) - chaine de dependances, tout compte
La chaine corniche -> porte -> coffret est inchangee, mais le teleporteur
exige desormais QUATRE piles : la photo « pile » materialisee par le coffret
n'est plus un bonus, elle est obligatoire. La vitrine v4 est une niche de
1.0 m de profondeur (portee d'interaction 1.7 m), pile a 0.5 m de
l'ouverture, fermee par un panneau lavande ; la pose du coffret depuis le
repere teal nord perce le panneau (et toute la niche : les cadres sombres se
decoupent aussi), son fond a 6 m tombant au bord du plateau. Trois reperes
guident les trois poses de la chaine ; gaspiller la corniche ou la porte
ailleurs bloque (R).

### 13. L'escalier sur l'escalier (2 piles) - une volee depuis une volee
> Ce niveau etait "La rampe celeste" et reposait entierement sur le fond
> peint vise vers le haut. Cette rampe est morte en v6.1 (section 1.4) : il
> n'existe aucun angle a la fois marchable et abordable. Le niveau a ete
> rebati sur le seul outil du budget que personne n'exploitait.

Une tour de 8.0 m au bout du plateau, deux piles a son sommet, et rien
d'autre pour y monter que deux photos d'escalier. Une volee posee du sol
plafonne a 4.62, soit 6.13 avec le saut : elle manque la tour de deux
metres. La seconde volee se pose DEPUIS LE PALIER DE LA PREMIERE (repere
corail au pied, palier autour de z = -5.2) et porte a 9.24 : le dernier
metre est une marche sur la face de la tour. La caisse est une marge, pas
une solution. La lecon : un point de pose est n'importe quel endroit ou
l'on tient debout, y compris quelque chose qu'on vient de poser.
Verrouille en moteur par la sonde (les deux volees sont posees et la
hauteur atteinte est mesuree au rayon), parce qu'une affirmation de ce
genre ne se demontre pas sur le papier.

### 14. La grande traversee (3 piles) - une route en quatre photos
Trois rives : depart, rive mediane (12 m de large), arrivee (pile +
teleporteur). Gouffre 1 (6 m) : passerelle depuis le repere teal ; son fond
peint coupe la rive mediane en deux, on passe par les flancs. Gouffre 2
(13 m) : depuis le repere corail au sud de la mediane, plancher de fond
(photo pile visee au sol, plan 7.4 x 7.4 a ~6.3 sous les pieds). v4 : la
pile dupliquee par cette pose TOMBE sur le plancher, et c'est la TROISIEME
pile requise : il faut descendre la chercher. Remontee : escalier pose du
plancher vers la rive (volee a -1.75), caisse posee sur la volee (corps
rigide : elle retombe sur la marche haute, +1.3), saut sur la rive.
Toute pose ratee au dessus du vide se paie d'un R : niveau d'engagement.

### 15. L'examen (5 piles) - tout, dans l'ordre qu'il faut
Cinq piles, cinq problemes, six photos, zero superflu : perchoir a 2.2
(corniche), cour fermee par le grand mur lavande (porte et sa regle des
6.2 m), vitrine-niche de 1.0 m (percee au mieux en y visant le coffret pose
ou la pile qu'il donne), tour a 3.3 (caisse posee, qui retombe au sol au
pied de la tour, puis console 180 a +2.37 et saut), duplication (coffret).
Le noeud est inchange : le coffret est DANS la cour, derriere la porte.
Quatre reperes au sol rythment les poses. v4 : chaque pose plante son fond
peint ; le plateau de 18 m les absorbe, mais l'ordre reste la seule carte.

## 4 bis. v3/v4 : l'appareil photo et les niveaux 16 a 20

### Mecanique (v4)

L'appareil est un objet ramassable qui charge la pellicule du niveau. Clic
gauche mains vides : la vue est capturee (frustum de pose, profondeur 12 m,
plan proche 0.5 m) en une **photo ordinaire** qui suit tout le pipeline
(levee 2D, rotation, pose, remplacement a la pose). Regles v4 :

- **La pellicule capture TOUT** : les blocs (plateformes, decors, lavande),
  les cages (une boite pleine a leur taille) et les piles. Tri par
  profondeur croissante, plafond de 32 props.
- **La capture consomme TOUJOURS un film**, meme cadree sur le ciel : la
  photo vide (props vides, fond ciel a 12 m) est un outil, pas un echec.
- **Le test est geometrique** : barreaux, murs et distances ne bloquent pas
  la prise de vue. C'est le puzzle du niveau 19.
- **Les copies posees sont des blocs ordinaires** : decoupables et
  rephotographiables. Les boites de 1.6 m ou moins par cote ("loose") et
  les piles deviennent des corps rigides a la pose : elles tombent.
- Le piege fondamental, enseigne au niveau 17 : PHOTOGRAPHIER copie, mais
  POSER remplace. Poser une copie face a son original detruit l'original.

### Les niveaux

- **16. Le cliche** (2 piles, 2 vues) : le niveau de la PHOTO VIDE. Le
  teleporteur et une pile sont enfermes dans une cage sombre a toit, et
  aucune photo classique n'existe au niveau. Cadrer le ciel (la pellicule
  part, la photo de rien arrive), poser depuis le repere corail face a la
  cage : elle casse, et le fond ciel de 12 m tombe dans le vide derriere la
  petite ile. La planche lavande du plateau de depart est un leurre : la
  photographier marche aussi, mais sa copie encombre le champ.
- **17. Copie de travail** (2 piles, 1 vue) : la MEME planche doit servir
  deux gouffres : elle ponte deja le premier ; la photographier depuis le
  repere teal (en plongee, pour ne cadrer qu'elle), traverser, puis poser la
  copie sur le second depuis le repere corail EN TOURNANT LE DOS a
  l'originale, sinon la pose la remplace et coupe le retour. Une seule vue :
  zero droit a l'erreur (R sinon).
- **18. L'echafaudage** (2 piles, 3 vues) : le niveau de la CHUTE. Une fosse
  de 2.4 m coupe la route (une pile plombee au fond) : on y descend, on n'en saute
  pas. Photographier une caisse lavande (1.4 m : "loose") depuis le repere
  teal, descendre, poser le cliche contre la paroi de sortie depuis le
  repere corail : la caisse copiee TOMBE au pied de la paroi et devient la
  marche (+1.4, saut 1.5 : sortie). Trois vues : deux marges d'erreur. La
  pose entaille la rive de sortie en son milieu ; les flancs restent.
- **19. A travers les barreaux** (3 piles, 2 vues) : deux piles encagees au
  sommet d'une tour-ile infranchissable (5 m de gouffre, 3 m de denivele).
  v4 : casser la cage est POSSIBLE (son centre est a ~9 m du bord) mais
  INUTILE : le gouffre reste. La solution : photographier les piles a
  travers les barreaux depuis le repere teal, puis poser le cliche face au
  plateau depuis le repere corail : les copies, corps rigides, TOMBENT a
  vos pieds. La cage copiee arrive en bloc plein avec elles : un perchoir
  gratuit.
- **20. Le studio** (4 piles, 2 vues + porte + corniche) : l'examen final.
  Un mur lavande (porte, repere corail ouest), un perchoir (corniche, repere
  teal est), une pile encagee (cage sombre : la photo VIDE la casse, repere
  teal sud), un ilot au dela d'un vide de 3 m (photographier la planche
  lavande de 4 m depuis le sud, la poser en pont depuis le repere corail :
  a 4 m elle n'est pas "loose", elle reste en place). Deux vues pour deux
  travaux de camera : l'economie est le dernier mot du jeu.

## 5. Ce que le jeu ne fait toujours pas (assume)

- La physique v4 ne concerne que les objets POSES (piles et petites boites
  "loose") : effacer le support d'un bloc du monde ne le fait toujours pas
  tomber.
- Les reperes au sol donnent le point ou se tenir, jamais l'angle : lire la
  photo levee (2D, molette pour le roulis) fait partie du jeu.
- Le sprint-saut (7.4 m) court-circuite certains fosses : tolere, les piles
  en hauteur et les denivelees restent les verrous reels.

## 6. Verification

- Suites unitaires etendues : catalogue a 8 photos, genre `photo`, compte
  recursif des piles (coffret = 1, garde anti-cycle), 20 niveaux, cages sur
  plateforme, solvabilite recursive de chaque niveau (monde + photos
  recursif + pellicule quand appareil et piles monde sont presents).
- Sonde `--smoke` etendue : rotation 180 verifiee au rayon (dalle a +2.37),
  effacement d'une cage au niveau 6, coffret qui materialise une photo,
  backdrop-plancher verifie au rayon apres pose piquee, R qui reconstruit le
  niveau courant.
