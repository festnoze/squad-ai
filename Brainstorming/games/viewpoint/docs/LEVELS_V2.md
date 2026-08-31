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

### 1.3 Photo dans la photo

Nouveau genre de prop `photo` : a la pose, il materialise un **objet photo
ramassable** (le meme PhotoItem que ceux places par le niveau). Chaine de
materialisation : poser A fait apparaitre la photo B, qu'on pose a son tour.
Le test de solvabilite compte les piles **recursivement** a travers ces
imbrications (garde anti-cycle).

### 1.4 Tangage assume (poser vers le bas / vers le haut)

Deja permis par l'ancre camera complete, jamais exige avant : viser vers le
bas incline la passerelle en plan descendant, et le **backdrop d'une photo
posee en regardant le sol devient un plancher** (quad perpendiculaire a la
visee, a 8 m). Les niveaux 10 et 14 en font le sujet.

### 1.5 Decoupage partiel et regle du scelle

Les blocs effacables ne disparaissent plus en bloc : la partie de leur volume
prise dans le frustum est decoupee (boite moins boite, 6 fragments au plus,
eux-memes effacables). Deux consequences de design :

- **Regle du scelle** : une photo qui contient un mur pleine trame (porte) ou
  un backdrop (pile) ne decoupe que **jusqu'au plan de ce scelle**, et le
  scelle remplit exactement la section du frustum a cette profondeur. Tout
  trou creuse devant est donc referme par le contenu : aucun interstice.
  Corollaire joueur : la porte ne decoupe qu'a moins de 6.2 m, il faut
  s'approcher. Un test unitaire (test_porte_seal) et un rayon de la sonde
  verrouillent cette regle.
- **Les sols aussi se decoupent** : viser un plancher lavande le perce.
  C'est un outil (niveau 11) et un danger (une pose negligente coupe la
  route ; R rattrape).

### 1.6 R : recommencer le niveau

Filet anti-blocage systemique : les photos sont consommables, un niveau
complexe peut donc etre gaspille. La touche R recharge le niveau courant
(memes definitions, inventaire remis a zero). Affiche dans le menu.

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
| Backdrop (pile) vise a ~50 deg vers le haut | rampe de pente ~40 deg | bord bas a ~5.4 m au dessus des pieds DU POSEUR : se pose du sol, s'aborde depuis un escalier (4.62 + saut) ; bord haut a ~10.1 |
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

## 4. Les niveaux 6 a 15

Chaque entree : intention, disposition, solution attendue, rattrapage.

### 6. La cage (2 piles) - decouvrir les cages effacables
Plateau simple. Une pile libre ; l'autre dans une cage lavande a toit.
Photo : porte ouverte. Cadrer la cage, poser : la cage disparait (les cages
n'ont pas de decoupe partielle, elles partent entieres).
Rattrapage : la porte efface aussi a 12 m, difficile de la gaspiller ; R sinon.

### 7. Pivot (2 piles) - decouvrir la rotation
Plateau central, deux perchoirs de part et d'autre d'une douve de 2 m,
hauteurs 2.2 (droite) et 3.0 (gauche). Deux photos corniche.
Solution : corniche a 0 deg (dalle a droite, +1.17) pour le perchoir droit ;
pour le gauche, corniche a 180 deg posee du sol (dalle a gauche, +2.37),
abordee depuis le bloc fixe du decor (1.5 de haut), puis saut final.
Rattrapage : R si une corniche est posee du mauvais cote.

### 8. Le coffret (2 piles) - decouvrir la photo dans la photo
Une pile libre. La photo coffret materialise un socle portant la photo
« pile », qu'on ramasse puis pose pour dupliquer la deuxieme pile.

### 9. L'enclos (2 piles) - cage permanente, entrer PUIS sortir
Enclos sombre sans toit (murs 2.8), une pile au centre, une console et une
caisse visibles A L'INTERIEUR a travers les barreaux. Escalier a l'exterieur.
Entrer : escalier pris a 6 m et plus, la volee passe au dessus du mur (3.15 au
droit du mur), on marche jusqu'au sommet (4.62) et on se laisse tomber dedans.
Sortir : caisse (+1.30), puis console 0 deg posee depuis la caisse (+2.47),
saut (+3.97) par dessus le mur.
Rattrapage : R remet l'escalier dehors si on l'a pose de travers.

### 10. Plongeon (2 piles) - poser en piquant vers le bas
Ilot bas 5 m sous le plateau de depart, 5.5 m en avant, hors de portee de
saut. Passerelle piquee a ~40 deg : plan incline qui descend jusqu'a l'ilot.
Le teleporteur et la deuxieme pile sont en bas.
Rattrapage : passerelle posee a plat = pont vers rien, R.

### 11. Sous le pont (2 piles) - les sols se decoupent
Deux iles reliees par une passerelle de sol LAVANDE (2 m de large), une
etagere etroite 4 m sous elle, invisible depuis le spawn. Pile 1 en haut
d'une tourelle sur l'ile d'en face (console 0 deg + saut). Pile 2 sur
l'etagere, sous le pont : il faut DELIBEREMENT percer le sol lavande (console
restante visee vers le pont, le frustum decoupe le plancher au dela de
3.6 m), tomber par le trou, et remonter par l'escalier pre-place sur
l'etagere (4.62 >= 4).
Danger enseigne : poser une photo face au pont AVANT de l'avoir traverse le
decoupe et coupe la route (R). L'ordre des poses est la lecon.

### 12. La vitrine (3 piles) - chaine de dependances
Chaque photo ouvre l'acces a la suivante : la corniche (au spawn) hisse sur
un perchoir a 2.2 qui porte la pile 1 ET la photo porte ; la porte perce le
grand mur lavande qui ferme la cour ouest (pile 2 + photo coffret) ; le
coffret, pose face a la VITRINE (niche a cadre sombre fermee par un panneau
lavande, pile 3 visible dedans), decoupe le panneau ET materialise la photo
pile en prime. La pile 3 se ramasse a travers la niche ouverte (portee
d'interaction 3.4 m, pas besoin d'entrer).
Difficulte : rien n'indique l'ordre ; gaspiller la corniche ou la porte
ailleurs bloque la chaine (R).

### 13. La rampe celeste (2 piles) - le backdrop devient une rampe
Une aiguille de 9.1 m au dela d'un vide de 6.5 m, pile 1 au sommet. Le
backdrop de la photo pile, vise vers le HAUT a ~50 deg depuis le bord du
plateau, se pose en rampe de pente ~40 deg (marchable) : bord bas a ~5.4 m au
dessus du point de pose, bord haut a ~10.1 m, huit metres en avant, contre
l'aiguille. Ordre impose par la geometrie : poser la rampe DU SOL d'abord,
monter ensuite l'escalier (4.62) pose a cote, sauter sur le bord bas (6.12 de
portee >= 5.4, la caisse donne de la marge), remonter la rampe, sauter sur
l'aiguille. Pile 2 libre au sol pour limiter la frustration.
Le niveau le plus exigeant en visee : entre 46 et 52 deg de tangage, tout
fonctionne ; en dehors, R.

### 14. La grande traversee (2 piles) - une route en trois photos
Vingt metres de vide en deux gouffres : rive de depart, ilot 4 x 4, rive
d'arrivee (pile 2 + teleporteur). Gouffre 1 (8 m) : passerelle, pile a
l'exact bord de portee. Gouffre 2 (13 m) : trop large pour tout, sauf le
plancher de backdrop vise vers le bas depuis l'ilot, puis remontee escalier
(-1.58 sous la rive) + caisse (-0.28) + saut. Les quatre photos partent de la
rive de depart : il faut les transporter une par une sur la passerelle et
choisir depuis ou poser chacune. Toute pose ratee au dessus du vide se paie
d'un R complet : c'est un niveau d'engagement.

### 15. L'examen (5 piles) - tout, dans l'ordre qu'il faut
Cinq piles, cinq problemes, six photos, zero superflu :
pile 1 sur un perchoir a 2.2 (corniche) ; pile 2 dans la cour fermee par un
grand mur lavande (porte, et sa regle des 6.2 m) ; pile 3 dans la vitrine a
panneau lavande ; pile 4 au sommet d'une tour a 3.3 (caisse pour aborder la
console 180 a +2.37, puis saut) ; pile 5 par duplication.
Le noeud : le coffret est DANS la cour (derriere la porte), et la vitrine se
perce au mieux en y visant le coffret ou la pile qu'il donne : porte, puis
coffret rapporte devant la vitrine, puis pile posee. Teleporteur a 5 piles :
fin du jeu.

## 5. Ce que la v2 ne fait toujours pas (assume)

- Pas de physique dynamique : rien ne tombe quand on efface son support.
- Pas d'appareil photo (reserve PRD section 9) ; la rotation et les photos
  imbriquees preparent le terrain (une capture produirait le meme
  dictionnaire).
- Le sprint-saut (7.4 m) court-circuite certains fosses : tolere, les piles
  en hauteur et les cages restent les verrous reels.

## 6. Verification

- Suites unitaires etendues : catalogue a 8 photos, genre `photo`, compte
  recursif des piles (coffret = 1, garde anti-cycle), 15 niveaux, cages sur
  plateforme, solvabilite recursive de chaque niveau.
- Sonde `--smoke` etendue : rotation 180 verifiee au rayon (dalle a +2.37),
  effacement d'une cage au niveau 6, coffret qui materialise une photo,
  backdrop-plancher verifie au rayon apres pose piquee, R qui reconstruit le
  niveau courant.
