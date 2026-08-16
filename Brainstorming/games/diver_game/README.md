# ABYSSE

Jeu de plongee sous-marine dans le navigateur. Vous etes biologiste marin sur
l expedition Kaloa: vous descendez avec le submersible, vous explorez un recif
qui plonge vers une fosse abyssale, vous capturez des especes inconnues, vous
les ramenez en soute, vous remontez, et vous allez les montrer a la scientifique
sur l ile. Chaque espece inedite vaut une medaille, et trois medailles ouvrent
une nouvelle combinaison de plongee.

Zero build, zero dependance a installer, aucun asset binaire. Tout est genere a
l execution: geometries, textures canvas, sons WebAudio.

## Lancer le jeu

```bash
cd Brainstorming/games/diver_game
python serve.py
```

Puis ouvrir http://localhost:8095/index.html

Le serveur fourni desactive le cache, ce qui evite de rejouer une ancienne
version apres une modification. Un simple `python -m http.server 8095` marche
aussi. Ouvrir `index.html` directement en `file://` ne marche pas, les modules
ES ont besoin d une origine http.

## Commandes

| Touche | Action |
|---|---|
| Z Q S D | Nager (6 degres de liberte, vous allez ou vous regardez) |
| Espace | Monter, sauter a terre |
| Ctrl ou C | Descendre |
| Maj | Palmage rapide (consomme de l endurance et de l oxygene) |
| Souris | Regarder |
| Clic gauche | Tirer |
| 1 2 3 4 | Harpon, fusil a aiguilles, baton electrique, lance-filet |
| Molette | Arme suivante ou precedente |
| R | Recharger |
| F | Lampe de plongee |
| E | Interagir (sous-marin, scientifique) |
| Tab | Carnet d especes |
| Echap | Pause |

Le clavier est lu par position physique, donc ZQSD en AZERTY et WASD en QWERTY
sont les memes quatre touches, sans reglage.

## Boucle de jeu

1. **Plonger.** Le submersible est amarre sur le recif. Vous partez avec une
   bouteille pleine, quatre outils et un filet de six places.
2. **Identifier.** Visez une creature quelques secondes: le scanner du masque
   affiche son nom et sa fiche. Identifier n est pas decouvrir, ca sert juste a
   savoir ce que vous avez en face.
3. **Capturer.** Deux facons. Le **lance-filet** (touche `4`) capture vivant, en
   un tir, tout ce qui mesure au plus 1,6 m et ne vous chasse pas activement,
   dans un rayon de 3,2 m autour du point d impact. Les capsules sont treuillees
   jusqu a vous et rentrent au filet toutes seules: c est l outil pour les
   bancs. Ce qui est trop gros, ou qui vous chasse, est seulement empetre cinq
   secondes et demie, sans une egratignure. Sinon, abattez la creature, le
   specimen flotte, nagez dedans pour le ramasser. Le filet plein, il faut
   rentrer.
4. **Decharger.** Approchez du sous-marin, `E` vide le filet en soute. Le
   sous-marin recharge aussi l oxygene, la sante et les munitions.
5. **Remonter.** Avec de la soute, `E` declenche la remontee. Vous voyagez a
   bord jusqu au ponton de l ile.
6. **Faire valider.** Marchez jusqu au laboratoire, `E` sur Dr. Vasseur. Chaque
   espece jamais rapportee entre au catalogue et vaut une medaille. Le palier
   des dix especes cataloguees paie une prime de deux medailles.
7. **Choisir une combinaison.** Toutes les trois medailles, le choix d une
   nouvelle livree s ouvre. Puis on redescend.

Mourir ne coute que le contenu du filet. La soute et le catalogue sont
conserves. La progression est sauvegardee dans le `localStorage`.

On n entre jamais dans le sous-marin a pied. On s en approche par n importe
quel cote (la portee se mesure sur toute la longueur de la coque), ce qui
recharge en continu la bouteille, la sante et les munitions. `E` decharge le
filet, un second `E` lance la remontee, et pendant le trajet vous etes a bord
et libre de regarder autour de vous.

## Se debarrasser d un predateur

Trois reponses, dans l ordre de fiabilite:

1. **Le baton electrique** (touche `3`). Contact uniquement, mais il assomme la
   cible plusieurs secondes puis la met en fuite. C est la seule arme qui rompt
   une attaque engagee.
2. **Le harpon**. Il tue, mais un requin de recif demande trois traits et un
   grand blanc huit. A ne tenter que si vous avez de la marge.
3. **Le sous-marin**. Amarrez-vous: les predateurs decrochent des que vous etes
   a quai. C est le refuge quand la bouteille est basse.

Ce qui vous fait reperer: tirer et palmer vite font du bruit, et etre blesse
laisse du sang qui elargit leur rayon de detection. Rester immobile et lampe
eteinte les calme.

## Le monde

Cinq zones, du plus clair au plus noir, reparties par profondeur:

| Zone | Profondeur | Ce qu on y trouve |
|---|---|---|
| Lagon corallien | 6 a 26 m | Coraux, anemones, poissons de recif, tortues |
| Foret de kelp | 20 a 50 m | Kelp anime, merous, raies manta |
| Arches rocheuses | 32 a 68 m | Arches franchissables, murenes, barracudas, requins de recif |
| Epave du Meroe | 48 a 82 m | Cargo brise en deux, rascasses, poulpes, requins-marteaux |
| Fosse abyssale | 70 a 170 m | Noir complet, meduses bioluminescentes, baudroies, calmar geant |

Seize especes au total. Les plus rares (grand requin blanc, baudroie abyssale,
calmar geant) n apparaissent que dans leur zone et rarement. Cinq especes
chassent activement le plongeur (requin de recif, requin-marteau, grand requin
blanc, baudroie abyssale, calmar geant): le sang et le bruit augmentent leur
rayon de detection, le baton electrique les fait fuir. Quatre autres piquent au
contact sans vous poursuivre (murene, barracuda, rascasse volante, meduse).

Quatre fosses percent le fond bien en dessous du relief qui les entoure, la
plus profonde a 166 m. Comme le biome se resout sur la profondeur, un trou
assez creuse abrite sa propre poche de vie abyssale au milieu d une zone
claire: c est la que se trouvent les baudroies sans avoir a traverser toute la
carte.

L oxygene descend d autant plus vite que vous etes profond. A la surface la
bouteille se recharge. Sous 30 pour cent de reserve, une alarme s affiche sous
le reticule avec le temps d air restant et le temps qu il faut pour remonter
depuis la profondeur ou vous etes.

## Architecture

```
index.html          DOM complet (HUD, ecrans, gestion d erreur)
styles.css          toute la presentation
serve.py            serveur statique sans cache
vendor/             three.module.js r169 vendorise
docs/CONTRACTS.md   contrat d interface entre modules
tools/smoke.mjs     test de bout en bout (Chrome headless via CDP)
src/
  config.js         table de reglages, especes, armes, combinaisons, biomes
  save.js           progression localStorage
  input.js          clavier et souris, pointer lock
  textures.js       toutes les textures generees en canvas 2D
  water.js          surface, caustiques, god rays, neige marine, brouillard, lumiere
  world.js          fond marin, rochers, kelp, coraux, epave, ile, laboratoire
  fauna.js          maillages proceduraux par espece, IA, combat, specimens
  diver.js          physique du plongeur, vitals, armes, view model, combinaison
  sub.js            submersible, amarrage, trajet recif vers ponton
  hud.js            ecrans, jauges, carnet, debrief scientifique
  audio.js          synthese WebAudio integrale
  main.js           boucle et machine a etats
```

Regle structurante: aucun module de gameplay n en importe un autre. Ils
n importent que `three` et `config.js`, recoivent leurs dependances en
parametre, et `main.js` cable les callbacks. `docs/CONTRACTS.md` est la source
de verite des interfaces.

## Verifier que tout marche

Avec le serveur lance dans un autre terminal:

```bash
node tools/smoke.mjs
```

Le script ouvre le jeu dans un Chrome headless, pilote la partie par le
protocole DevTools et deroule toute la progression: tuer trois especes, les
ramasser, les decharger en soute, remonter avec le sous-marin, debarquer sur
l ile, passer le debriefing, gagner les medailles, debloquer et equiper une
combinaison, redescendre. Il verifie ensuite qu un predateur mord bien, que la
mort et la reapparition marchent, que le carnet et la pause s ouvrent, et que
le palier des dix especes paie sa prime. Sortie non nulle des qu une
verification echoue ou qu une erreur JavaScript apparait. Les captures d ecran
atterrissent dans `.smoke/`.

Chrome headless tombe sur un rendu logiciel, donc la scene y tourne a bien
moins d une image par seconde. Le script n attend jamais un delai fixe, il
attend toujours que la boucle de jeu ait effectivement avance.

## Reglages

Tout se regle dans `src/config.js`: vitesses de nage, consommation d oxygene,
degats et cadence des armes, table des especes (profondeur, comportement,
rarete, valeur), progression des medailles, densite des effets.

Pour tester rapidement, `DEBUG.spawnAll = true` fait apparaitre une creature de
chaque espece pres du point de depart.
