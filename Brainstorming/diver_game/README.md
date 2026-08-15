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
cd Brainstorming/diver_game
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
| 1 2 3 | Harpon, fusil a aiguilles, baton electrique |
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
   bouteille pleine, trois armes et un filet de six places.
2. **Identifier.** Visez une creature quelques secondes: le scanner du masque
   affiche son nom et sa fiche. Identifier n est pas decouvrir, ca sert juste a
   savoir ce que vous avez en face.
3. **Capturer.** Abattez la creature, le specimen flotte, nagez dedans pour le
   mettre au filet. Le filet plein, il faut rentrer.
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

## Le monde

Cinq zones, du plus clair au plus noir, reparties par profondeur:

| Zone | Profondeur | Ce qu on y trouve |
|---|---|---|
| Lagon corallien | 6 a 26 m | Coraux, anemones, poissons de recif, tortues |
| Foret de kelp | 20 a 50 m | Kelp anime, merous, raies manta |
| Arches rocheuses | 32 a 68 m | Arches franchissables, murenes, barracudas, requins de recif |
| Epave du Meroe | 48 a 82 m | Cargo brise en deux, rascasses, poulpes, requins-marteaux |
| Fosse abyssale | 70 a 132 m | Noir complet, meduses bioluminescentes, baudroies, calmar geant |

Seize especes au total. Les plus rares (grand requin blanc, baudroie abyssale,
calmar geant) n apparaissent que dans leur zone et rarement. Trois d entre elles
chassent activement le plongeur: le sang et le bruit augmentent leur rayon de
detection, le baton electrique les fait fuir.

L oxygene descend d autant plus vite que vous etes profond. A la surface la
bouteille se recharge.

## Architecture

```
index.html          DOM complet (HUD, ecrans, gestion d erreur)
styles.css          toute la presentation
serve.py            serveur statique sans cache
vendor/             three.module.js r169 vendorise
docs/CONTRACTS.md   contrat d interface entre modules
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

## Reglages

Tout se regle dans `src/config.js`: vitesses de nage, consommation d oxygene,
degats et cadence des armes, table des especes (profondeur, comportement,
rarete, valeur), progression des medailles, densite des effets.

Pour tester rapidement, `DEBUG.spawnAll = true` fait apparaitre une creature de
chaque espece pres du point de depart.
