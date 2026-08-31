# GOAL - Séance de tirs au but

Un jeu de penalty écrit en GDScript pour **Godot 4.7**. Un grand stade en plein
jour, un point à onze mètres, et un gardien piloté par l'application qui ne
triche pas : il lit votre langage corporel, il parie, et parfois il gagne son
pari.

Le terrain, le stade, la foule, le ballon et les 25 effets sonores sont
**générés par code** au démarrage. Les deux personnages utilisent un modèle
humain riggé commun et des textures de tenue dédiées : maillot et short réalistes,
sponsors fictifs et numéros de joueur. Les détails de provenance sont dans
`assets/CREDITS.md`.

## Lancer le jeu

Sous Windows, double-cliquez sur **`run.bat`**. Il se place tout seul dans le
dossier du jeu, trouve `godot.exe` sur le `PATH` (ou aux emplacements
d'installation habituels), et ne laisse la fenêtre ouverte qu'en cas d'erreur.
Si votre Godot est ailleurs, pointez-le avec `set GODOT=C:\chemin\godot.exe`.

```bash
# ou à la main, depuis games/goal
godot --path .
```

Ou ouvrir le dossier dans l'éditeur Godot et appuyer sur F5.

## Le tir

Un penalty se joue en trois décisions simultanées, et c'est là qu'est le jeu.

1. **La visée.** La souris déplace le réticule sur le but. Le réticule montre où
   le ballon irait **sans effet**. Il peut sortir du cadre : c'est comme ça qu'on
   tire à côté.
2. **La puissance.** Maintenez le tir : la barre se remplit. Un tir fort est plus
   dur à arrêter mais moins précis, et le haut de la barre achète de moins en
   moins de vitesse.
3. **La frappe.** Pendant que la barre se remplit, un curseur balaye la fenêtre
   de frappe propre. Relâcher **dans** la fenêtre donne un contact franc.
   Relâcher à côté, c'est une frappe manquée, et l'erreur grandit avec la
   puissance.

Ajoutez l'effet avec `A` et `E` (l'enroulé latéral) et le lift avec la visée
verticale (rétro pour flotter, lifté pour piquer). Le HUD dessine la trajectoire
prévue en direct : elle se courbe sous vos yeux quand vous montez l'effet.

Pendant la course d'élan, `Maj` fait une **feinte de frappe** (deux au maximum).
Elle retarde le contact et brouille la lecture du gardien. C'est l'arme contre un
gardien qui parie tôt.

## Le gardien

Il ne connaît jamais votre tir. Il ne voit que deux choses : votre langage
corporel avant la frappe (angle de course, pied d'appui, orientation des
hanches, feintes) puis les premières fractions de seconde du vol.

Et c'est un problème arithmétique pour lui. Un penalty à 28 m/s met **0,42 s** à
arriver. Le temps de réaction humain est de 0,2 s, et un plongeon complet jusqu'au
poteau prend 0,6 s. **Un gardien qui attend ne peut pas atteindre une lucarne.**
Il doit donc parier avant la frappe, et un pari perdu laisse le but grand ouvert.

Ce qui change avec le niveau, ce n'est jamais la physique : c'est la qualité de
la lecture, la vitesse du plongeon et l'allonge.

| Niveau | Ce qui change |
|---|---|
| Débutant | lit mal, réagit tard, plonge court |
| Confirmé | lit correctement les tirs mal masqués |
| Pro | réactions rapides, allonge sérieuse, paris bien choisis |
| Légende | lit presque tout ce qui dépasse, et sort des arrêts réflexes |

## Vous dans les gants (mode Duel)

En **Duel**, les rôles alternent : vous tirez un tour, vous gardez le suivant. La
caméra passe derrière le but, et le même corps que pilotait l'ordinateur passe
entre vos mains - même allonge, même vitesse de plongeon, même volume de parade.

### Les commandes

Aucune touche nouvelle : les trois entrées du tireur changent de métier.

| Entrée | Ce qu'elle fait côté gardien |
|---|---|
| Souris | déplace le **réticule de plongeon** dans la cage |
| Flèches gauche / droite | vous déplace sur votre ligne, 90 cm de chaque côté |
| Clic gauche ou `Espace` | **plonge**, une seule fois, définitivement |

Le réticule est bridé à l'intérieur du cadre : un plongeon visé au-dessus de la
barre n'est pas une décision, c'est une commande perdue.

### L'anneau bleu, et pourquoi il rétrécit

L'anneau dessiné dans la cage est votre **enveloppe de portée** : tout ce qu'un
plongeon lancé *maintenant* atteint encore. Ce n'est pas une illustration, c'est
la règle elle-même, tracée en cherchant à la dichotomie où votre marge s'annule.
Le pourcentage **COUVERTURE** à côté est la part du but que cet anneau couvre.

Il rétrécit pendant toute la course d'élan, et il ne repousse jamais. C'est
l'arithmétique du gardien vue de l'autre côté : **0,42 s** de vol, **0,2 s** de
réflexe, **0,6 s** de plongeon jusqu'au poteau. Ces trois nombres ne rentrent pas
les uns dans les autres. Attendre de savoir, c'est déjà avoir perdu la lucarne.

Tant que le tireur court, le jeu suppose un vol de 0,42 s, parce que personne ne
peut savoir mieux. **Une fois la frappe partie, il utilise le temps de vol réel** :
l'anneau s'effondre beaucoup plus vite sur une frappe sèche que sur un tir
mou - et cette différence-là se lit à l'œil.

Le réticule change de couleur avec la marge : il vous dit si *ce* plongeon-là est
encore jouable, quand l'anneau vous dit ce qui l'est en général.

### Ce que vous avez le droit de lire

Le panneau **LECTURE / ÉLAN** en bas à gauche est le langage corporel du tireur,
livré indice par indice à mesure qu'il approche. Il est dégradé par construction
et **son intention n'atteint jamais l'écran** : le plan du tireur reste dans le
moteur, vous n'en voyez que ce qu'un gardien verrait.

### Deux règles qui vous surprendront

- **Votre temps de réaction n'est pas facturé.** Le gardien de l'ordinateur le
  paie parce qu'il décide à un instant où son corps n'a pas encore bougé ; vous,
  vous avez déjà réagi quand vous cliquez. Le compte à rebours part du clic.
- **Votre place sur la ligne est la seule chose que le tireur sait de vous.** Il
  la regarde une fois, juste avant de se retourner et de courir, et il choisit sa
  cible avec. Se décaler est une vraie arme, et un vrai risque.

Enfin, le réglage de difficulté vaut pour **les deux bouts** : un duel contre une
Légende est un duel où vous gardez avec un corps de Légende.

## Le ballon

La trajectoire n'est pas une parabole. Le ballon subit une **traînée quadratique
avec crise de traînée** (le coefficient s'effondre quand la couche limite devient
turbulente, ce qui est exactement pourquoi une frappe puissante sans effet flotte)
et une **force de Magnus** proportionnelle à l'effet. Le tout est intégré en RK4
à 120 Hz.

Conséquences que vous sentirez en jouant : un tir à 30 m/s perd un quart de sa
vitesse sur onze mètres, un enroulé à 9 tours par seconde dévie d'un demi-mètre,
le rétro fait flotter et le lifté fait piquer.

Le ballon est un vrai **icosaèdre tronqué** (12 pentagones, 20 hexagones), pas une
sphère UV, et il tourne réellement autour de son axe d'effet. C'est comme ça que
vous lisez la courbe en vol.

## Modes

- **Séance de tirs au but** : cinq tirs, puis mort subite. L'équipe adverse tire
  aussi, contre votre gardien.
- **Entraînement** : tirs illimités, statistiques, aucun enjeu.
- **Défi** : des cibles dans le but, des points, et une série à ne pas casser.
- **Duel** : les rôles alternent, un tour vous tirez, un tour vous gardez. Voir
  « Vous dans les gants » plus haut.
- **Entraînement gardien** : le Duel sans le Duel. Vous gardez **chaque** tir, il
  n'y a pas de série à perdre, et l'ordinateur enchaîne les penalties tant que
  vous restez. Le bandeau compte vos arrêts sur le nombre de tirs affrontés.

  C'est là qu'on apprend à lire l'anneau, parce qu'on peut se tromper vingt fois
  de suite sans que ça coûte quoi que ce soit. La difficulté vaut toujours pour
  les deux bouts : à *Légende*, vous gardez avec un corps de Légende contre un
  tireur de Légende.

## Commandes

| Touche | Action |
|---|---|
| Souris | viser |
| Clic gauche / `Espace` | maintenir pour armer, relâcher pour tirer |
| `A` / `E` | effet à gauche / à droite |
| `Z` `S` / flèches haut bas | lift (rétro / lifté) |
| `Maj` | feinte de frappe pendant la course |
| Souris | *(Duel, gardien)* viser le plongeon |
| Flèches gauche / droite | *(Duel, gardien)* se déplacer sur la ligne |
| Clic gauche / `Espace` | *(Duel, gardien)* plonger |
| `C` | changer de caméra |
| `R` | revoir le tir |
| `Entrée` | tir suivant |
| `Échap` | pause |
| `F11` | plein écran |
| `F5` | recommencer |

Le plein écran est retenu d'une session à l'autre : le jeu rouvre comme vous
l'avez laissé.

## Développement

```bash
# suites unitaires, sans fenêtre
godot --headless --path . --script res://tests/run_tests.gd

# sonde d'intégration, dans le vrai jeu
godot --headless --path . -- --smoke

# mesure de l'équilibrage du gardien (long : environ 25 minutes)
godot --headless --path . -- --balance

# captures automatiques : 18 vues, du menu au portrait
godot --path . -- --shot C:\out

# réparation de l'atlas de peau (mesure seule sans --write)
godot --headless --path . --script res://tools/repair_skin_atlas.gd -- --write
```

`--shot` couvre les trois moitiés du jeu et pas seulement la première :

| Vues | Ce qu'elles montrent |
|---|---|
| 1 à 10 | le tour où **vous tirez** : menu, visée, course, vol, but, arrêt, gros plan de la prise, ralenti, télévision |
| 11 à 15 | le tour où **vous gardez** : placement, lecture, engagement, plongeon, verdict |
| 16 à 18 | les **portraits**, objectif à un mètre du visage |

Les portraits ne sont pas décoratifs. À distance de match un visage fait quarante
pixels de haut, donc rien de ce qui va mal sur une texture de peau n'est visible
sur les dix premières vues. C'est ainsi qu'un fond rouille sur la tempe et une
nuque non peinte ont survécu à plusieurs relectures.

`docs/CONTRACTS.md` est la **source de vérité** du projet : chaque module a été
écrit indépendamment par un agent différent, contre les signatures figées dans ce
document. Si vous modifiez une signature, modifiez le contrat d'abord.

Rappel de piège : sous `--script`, Godot n'enregistre pas les autoloads
(`Game`, `Shootout`, `Sfx`). Une suite de `tests/` ne doit donc jamais les
nommer, sinon elle ne compile pas. Tout ce qui a besoin du jeu vivant passe par
`tests/smoke_probe.gd`.

Second piège, celui-là silencieux : **ni le jeu ni les portes ne réimportent une
texture modifiée**. Godot ne reconstruit `.godot/imported/` qu'à l'ouverture de
l'éditeur, donc un `--shot` lancé après avoir réécrit un PNG rend l'ancienne
version sans rien dire. Après toute retouche d'un fichier de `assets/` :

```bash
godot --headless --path . --import
```
