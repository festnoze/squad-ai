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

## Commandes

| Touche | Action |
|---|---|
| Souris | viser |
| Clic gauche / `Espace` | maintenir pour armer, relâcher pour tirer |
| `A` / `E` | effet à gauche / à droite |
| `Z` `S` / flèches haut bas | lift (rétro / lifté) |
| `Maj` | feinte de frappe pendant la course |
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

# captures automatiques
godot --path . -- --shot C:\out
```

`docs/CONTRACTS.md` est la **source de vérité** du projet : chaque module a été
écrit indépendamment par un agent différent, contre les signatures figées dans ce
document. Si vous modifiez une signature, modifiez le contrat d'abord.

Rappel de piège : sous `--script`, Godot n'enregistre pas les autoloads
(`Game`, `Shootout`, `Sfx`). Une suite de `tests/` ne doit donc jamais les
nommer, sinon elle ne compile pas. Tout ce qui a besoin du jeu vivant passe par
`tests/smoke_probe.gd`.
