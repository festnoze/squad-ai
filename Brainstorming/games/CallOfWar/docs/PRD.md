# PRD - CALL OF WAR v2 « Maquis »

Document de cadrage produit. Version 1.0, 2026-08-23. Il propose et priorise
les évolutions du jeu à partir de l'état réellement livré (v1), pas d'une
vision idéale. Chaque exigence est écrite pour être vérifiable par le harnais
du projet (suites unitaires, sonde `--smoke`, captures `--shot`).

Règles d'écriture héritées du projet : texte joueur en français, code en
anglais, jamais de tiret cadratin, toute signature inter-module passe d'abord
par `docs/CONTRACTS.md`.

---

## 1. État des lieux (v1, mesuré)

Ce qui existe et fonctionne, chiffres vérifiés :

| Domaine | État |
|---|---|
| Monde | 4096 m x 4096 m, 22 sites, 8 secteurs, streaming 64 m, 4 LOD, pire frame 13.3 ms |
| Campagne | ~26 objectifs en 8 chaînes, 8 types d'objectifs, sauvegarde JSON |
| Armes | 7 armes + grenade, balistique avec pénétration, munitions par calibre |
| IA | 10 états, 6 rangs, escouades, suppression, budgets 60 soldats / 14 escouades |
| Rendu | 13 sets PBR CC0 + atlas de brins alpha, repli procédural intégral |
| Audio | 49 échantillons synthétisés (344 ms de build), pool 12 + 24 voix |
| UI | HUD complet, carte, journal, pause, style « papier militaire 1942 » |
| Tests | 6409 vérifications unitaires + 570 d'intégration, 0 échec |

### Dettes constatées (vérifiées dans le code le 2026-08-23)

Ces points ne sont pas des idées d'amélioration : ce sont des promesses de
l'interface actuelle qui ne sont pas tenues.

- **D1. La musique n'existe pas.** `Game.music_volume` est persisté et le menu
  pause affiche un curseur « Volume de la musique » (`pause_menu.gd:263`), mais
  aucun module ne lit cette valeur ni ne joue de musique. Le curseur ment.
- **D2. Les jumelles n'existent pas.** L'action `binoculars` (touche B) est
  installée dans l'InputMap et documentée dans le README (« B | jumelles »),
  mais aucun module ne l'écoute. La touche ne fait rien.
- **D3. Le sniper de l'Axe n'a pas de lunette.** La table d'armes n'a ni Luger
  ni Kar98k à lunette. Conséquences : le tireur d'élite allemand tire avec un
  Kar98k ouvert (donc sans le masque de lunette ni le zoom x4 côté joueur qui
  le ramasse), et l'officier allemand porte une MP40 faute de pistolet de
  l'Axe (contournement du 2026-08-23, historiquement passable mais pauvre).
- **D4. Le démarrage coûte 2.3 à 3.2 s.** Mesuré : la génération synchrone des
  9 tuiles de spawn est dominée par `Heightfield.color_at` (71 us/appel) et
  `normal_at` (61 us/appel), appelés par sommet alors que la grille de
  hauteurs est déjà échantillonnée.
- **D5. Le feuillage des arbres est resté procédural.** Canopées en ellipsoïdes
  pleins (« parasols »), en décalage de qualité avec le sol et les bâtiments
  désormais texturés. Chantier signalé en fin de v1.

---

## 2. Vision et objectifs

**Vision v2 :** transformer un très bon socle de simulation en un jeu qui se
**termine avec plaisir** : l'infiltration doit être un vrai style de jeu (pas
seulement tirer de loin), la campagne doit répondre aux actions du joueur
(contre-attaques, renseignement), et les 4 km de bocage ne doivent jamais être
une corvée de marche.

Objectifs mesurables :

1. Zéro promesse d'interface non tenue (D1 à D3 fermées).
2. Une partie furtive complète est possible : libérer un secteur sans
   déclencher l'alerte générale doit être faisable et récompensé.
3. Temps de trajet subi < 90 s entre deux points quelconques de la campagne
   (voyage rapide entre secteurs libérés).
4. Démarrage < 1.5 s sur la machine de référence.
5. Les suites restent vertes : toute fonctionnalité nouvelle arrive avec ses
   vérifications (unitaires si pur, sonde sinon).

### Non-objectifs (v2)

- **Pas de multijoueur.** Rien dans l'architecture n'est répliqué.
- **Pas de véhicules pilotables en v2** (voir P2 : le risque physique + IA est
  disproportionné tant que l'infanterie n'est pas finie).
- **Pas de nouveau biome ni d'agrandissement de la carte.** 4 km x 4 km est le
  bon format ; on densifie, on n'étale pas.
- **Pas de refonte de l'animation squelettale.** Les corps en boîtes animés
  par code sont un choix d'identité visuelle assumé.
- **Pas de contenu historique sensible.** Le jeu reste une uchronie légère
  (une « poche » fictive en 1942) ; pas de symboles interdits, pas de camps
  représentés au-delà de la libération de prisonniers déjà présente.

---

## 3. Priorisation

| ID | Fonctionnalité | Priorité | Taille | Motif |
|---|---|---|---|---|
| F1 | Jumelles (touche B) | **P0** | S | Dette D2, touche déjà documentée |
| F2 | Couche musicale par états | **P0** | M | Dette D1, le curseur ment |
| F3 | Luger + Kar98k à lunette | **P0** | M | Dette D3, change le contrat |
| F4 | Démarrage < 1.5 s | **P0** | S | Dette D4, gain mesurable |
| F5 | Infiltration complète | **P1** | L | Le plus gros gain de gameplay |
| F6 | Contre-attaques allemandes | **P1** | M | La campagne répond au joueur |
| F7 | Voyage rapide | **P1** | S | Anti-corvée, infra déjà en place |
| F8 | Renseignement et caches | **P1** | M | Récompense l'exploration |
| F9 | Compagnons résistants | **P1** | L | Fantasme central du thème |
| F10 | Débriefing de fin de campagne | **P1** | S | La victoire actuelle est plate |
| F11 | Feuillage en cartes alpha | **P2** | L | Dette D5, purement visuel |
| F12 | Accessibilité et manette | **P2** | M | Remap, daltonisme, sous-titres |
| F13 | Sauvegardes multiples + mode Fer | **P2** | S | Confort et rejouabilité |
| F14 | Localisation anglaise | **P2** | M | Toute l'UI est en dur en français |
| F15 | Véhicule pilotable | **P2** | XL | Reporté, risque disproportionné |

Tailles : S < 1 journée-agent, M = 1 à 2, L = 3 à 5, XL > 5.

---

## 4. Spécifications P0

### F1. Jumelles (touche B)

**Histoire.** En reconnaissance, je repère un site à 400 m : je veux compter la
garnison et localiser le mât radio avant de choisir mon angle d'attaque, sans
gaspiller les 5 coups de ma Springfield.

**Exigences.**
- B bascule la vue jumelles : zoom x8 (FOV / 8, borné à 10 degrés minimum),
  sensibilité souris divisée d'autant, masque binoculaire (deux cercles
  sécants) dessiné par le HUD en `_draw()`, graduations de distance.
- Incompatible avec : visée, arme d'épaule levée, rechargement, pansement,
  affût monté. Tirer, courir ou reprendre l'arme ferme les jumelles.
- Le HUD affiche la distance du point visé (raycast existant de `Ballistics`)
  et le nom du site le plus proche dans le cercle (via `Layout.nearest_site`).
- Aucune nouvelle signature de contrat : tout tient dans `Player` (état
  `is_scoping` privé + une variable publique lisible par le HUD, comme
  `prompt_text`) et dans `Hud`.

**Critères d'acceptation.**
- Sonde : simuler l'action B, vérifier que le FOV de la caméra a changé et
  qu'il revient à `Game.fov` à la fermeture.
- Capture : une vue jumelles sur l'aérodrome, à valider à l'oeil.
- Le README documente le comportement réel.

### F2. Couche musicale par états

**Histoire.** La tension doit s'entendre : quand une patrouille me cherche, je
veux le savoir sans regarder l'indicateur d'alerte.

**Exigences.**
- Nouveau module `src/audio/music.gd` (autoload ou enfant de Main, à trancher
  au contrat) : nappes et percussions **synthétisées par `SfxLib`** (le projet
  sait déjà faire), pas de fichier audio.
- Quatre états, pilotés par `War.alert_level` et le combat effectif :
  `CALM` (silence ponctué : nappe rare, < 20 % du temps), `SEARCH` (percussion
  sourde lente), `COMBAT` (couche rythmique + cuivres de synthèse), `VICTORY`
  (motif court à la capture d'un secteur, one-shot).
- Fondu enchaîné 2 à 4 s entre états. Bus audio dédié `Music`, volume branché
  sur `Game.music_volume` (le curseur existant devient vrai).
- Le silence est un choix esthétique : en jeu calme, la musique doit être
  absente la majorité du temps. C'est un jeu d'ambiance, pas un juke-box.

**Critères d'acceptation.**
- Unitaire : les nouveaux échantillons de `SfxLib` construisent, format 16
  bits mono, normalisés (la suite `test_sfx_lib` les couvre automatiquement
  s'ils rejoignent `NAMES`).
- Sonde : forcer `War.raise_alert(3)`, vérifier que l'état musical suit ;
  mettre `music_volume` à 0, vérifier le silence total.

### F3. Luger P08 et Kar98k à lunette

**Histoire.** Je tue le tireur d'élite du clocher et je ramasse son arme : je
veux sa lunette. Je fouille un officier : je veux son Luger, pas une MP40.

**Exigences.**
- Deux nouveaux ids dans `WeaponDefs` : `LUGER := 8` (9 mm, chargeur 8,
  semi-auto, 30 dmg) et `KAR98K_SCOPED := 9` (identique au Kar98k + lunette
  x4, rechargement coup par coup car le chargeur-lame ne passe pas la
  lunette). `COUNT := 10`.
- **Procédure de contrat** : mettre à jour `docs/CONTRACTS.md` section 2.19
  AVANT le code ; les ids existants ne bougent pas (append-only, les
  sauvegardes stockent des ids).
- `Soldier._pick_weapon` : officier de l'Axe → Luger (annule le contournement
  MP40 du 2026-08-23) ; sniper de l'Axe → Kar98k à lunette.
- `Meshes.weapon_model` : silhouette Luger (canon fin, pontet rond, crosse
  inclinée) et Kar98k surmonté d'une lunette.
- Le Luger partage le calibre 9 mm de la MP40 (`ammo_type` 2) : butin utile.

**Critères d'acceptation.**
- `test_weapon_defs` passe sans modification de sa logique (il itère sur
  `all_ids()`) ; ajouter un cas : le sniper de l'Axe a `has_scope` vrai.
- Sonde : un officier de l'Axe tué laisse un `pickup` d'id `LUGER`.

### F4. Démarrage < 1.5 s

**Exigences.**
- Dans `TerrainChunk.build_data`, calculer couleur et normale **depuis la
  grille de hauteurs déjà échantillonnée** (différences finies sur les 33x33
  points) au lieu de rappeler `color_at`/`normal_at` par sommet, qui refont
  chacun leurs propres appels de bruit.
- `color_at` reste la référence : la version grille doit s'en écarter de moins
  d'un epsilon perceptif (la teinte par biome est déjà de basse fréquence).
- Cible : prime de spawn < 1.5 s, mesuré par le chrono déjà loggé.

**Critères d'acceptation.**
- `test_heightfield` inchangé et vert (la fonction de référence ne bouge pas).
- Mesure avant/après consignée dans le message de commit.
- Aucune couture visible entre tuiles sur les captures (la couleur par grille
  doit échantillonner les mêmes points aux bords).

---

## 5. Spécifications P1

### F5. Infiltration complète

L'existant : bruit du joueur (`noise_radius`), vue réduite la nuit et par
météo, coup de crosse dans le dos déjà létal (55 x 3 = 165 > 130 PV max).
Ce qui manque : les conséquences et les récompenses.

**Exigences.**
- **Silence du takedown** : un coup de crosse qui tue une cible non alertée
  (état IDLE, PATROL ou ALERT sans cible) n'émet aucun bruit IA et ne fait pas
  crier la victime (`german_death` remplacé par un râle court à -12 dB).
- **Découverte des corps** : un soldat dont le cône de vision contient un
  cadavre de sa faction passe en `S_ALERT`, alerte son escouade
  (`report_contact` sur la position du corps) et monte `War.raise_alert(2)`.
  Un corps déjà découvert ne compte qu'une fois (marqueur sur le noeud).
- **L'alarme a une source** : détruire le mât radio d'un site (ancre `radio`
  déjà exposée) AVANT d'être repéré coupe les renforts de ce site : le
  Director n'envoie pas de vague vers ce secteur tant que l'alerte vient de
  lui. Le HUD l'annonce (« Radio détruite : la garnison est isolée »).
- **Récompense** : capturer un secteur sans avoir dépassé l'alerte RECHERCHE
  affiche une bannière dédiée (« Secteur libéré en silence ») et crédite une
  statistique `silent_captures` dans `War`.

**Critères d'acceptation.**
- Sonde étendue : tuer un soldat isolé par derrière via l'API, vérifier que
  l'alerte reste CALME ; placer un second soldat face au corps, vérifier le
  passage à RECHERCHE.
- `War.to_dict`/`from_dict` transportent la nouvelle statistique (clé absente
  tolérée : sauvegardes v1 lisibles).

### F6. Contre-attaques allemandes

**Exigences.**
- Après une capture, le Director peut planifier UNE contre-attaque sur ce
  secteur (probabilité 40 %, entre 6 et 14 minutes de jeu plus tard, jamais
  pendant qu'un objectif à limite de temps est actif).
- Annonce par radio (toast + son `german_alert` lointain) 90 s avant, puis
  2 à 3 escouades convergent (budgets globaux inchangés : la contre-attaque
  puise dans les 14 escouades, elle ne s'y ajoute pas).
- Si le joueur (ou ses compagnons, voir F9) élimine l'assaut : bannière,
  bonus de munitions à la planque. S'il est absent ou meurt : le secteur
  devient **contesté** (icône carte, garnison réduite réapparaît, la chaîne
  d'objectifs du secteur reste acquise : seule la reprise de zone O_CAPTURE
  est rejouée). Un secteur contesté ne re-déclenche jamais `war_won` à
  l'envers : `War.capture_sector` reste idempotent, on ajoute un état
  `contested` séparé.
- Plafond : jamais plus d'une contre-attaque active, jamais sur le village de
  départ.

**Critères d'acceptation.**
- Sonde : forcer une contre-attaque via une méthode de debug du Director,
  vérifier le respect des budgets et l'état contesté après échec simulé.
- Sauvegarde : un secteur contesté survit au rechargement.

### F7. Voyage rapide

**Exigences.**
- Sur la carte (M), cliquer un secteur **libéré et non contesté** propose le
  voyage (bouton contextuel). Conditions : alerte CALME, pas de combat à
  moins de 80 m, pas d'objectif à limite de temps actif.
- Transition : fondu au noir 1 s, avance de l'heure de 12 à 20 minutes de jeu
  (le temps du trajet), arrivée à la planque du secteur (position de respawn
  déjà calculée par `_friendly_respawn`).
- Le monde stream autour de l'arrivée AVANT de rendre la main (réutiliser la
  garde `is_ground_ready`, déjà éprouvée).

**Critères d'acceptation.**
- Sonde : voyage forcé, vérifier position finale au-dessus du sol, aucune
  frame sans collision, heure avancée.

### F8. Renseignement et caches

**Exigences.**
- **Caches de la Résistance** : chaque secteur libéré équipe sa planque d'une
  caisse (`interact`) qui recharge munitions et grenades aux maximums, avec
  un délai de réutilisation de 5 minutes de jeu (pas un distributeur infini).
- **Documents** : les officiers portent des documents (`pickup` au sol à leur
  mort, à côté de l'arme). Les ramasser révèle sur la carte la garnison
  restante et les ancres d'objectif du secteur d'origine de l'officier, et
  crédite `intel_found` dans `War`.
- Les objectifs O_RECON existants créditent aussi `intel_found`.

**Critères d'acceptation.**
- Sonde : tuer un officier via l'API, vérifier le pickup document ; le
  ramasser, vérifier l'exposition carte (structure de données, pas le dessin).

### F9. Compagnons résistants

**Exigences.**
- Dans chaque secteur libéré, 1 à 2 résistants « recrutables » (invite E :
  « Rejoindre le maquis »). Maximum 2 compagnons simultanés.
- Ordres minimaux, sans UI nouvelle : E sur un compagnon bascule
  suivre / tenir la position. Ils utilisent `Squad` allié existant (faction
  `War.ALLIED`, l'IA de combat est déjà là) avec un mode « suivre un noeud ».
- Règles de tir : jamais à travers le joueur (la ligne de vue IA l'exclut
  déjà), pas de tir si le joueur est furtif (alerte CALME) sauf si le joueur
  tire d'abord.
- Mort définitive, remplaçable dans un secteur libéré. Pas de réanimation.
- Ils ne montent pas en voyage rapide s'ils sont à plus de 30 m (ils sont
  laissés sur place, toast d'avertissement).

**Critères d'acceptation.**
- Sonde : recruter via l'API, vérifier le suivi (distance bornée après 30 s
  de marche), l'ordre « tenir », et le plafond de 2.
- Budgets Director inchangés (les compagnons comptent dans le budget allié).

### F10. Débriefing de fin de campagne

**Exigences.**
- À `war_won` : écran dédié (nouvelle vue plein écran, style papier) :
  durée, kills, précision, tirs à la tête, captures silencieuses, morts,
  documents trouvés, par secteur : temps et style (assaut / silencieux).
- Deux boutons : « Continuer à explorer » (le monde reste jouable, le
  Director cesse les contre-attaques) et « Nouvelle campagne » (nouvelle
  graine, confirmation à double clic comme le menu pause).

**Critères d'acceptation.**
- Sonde : forcer `war_won`, vérifier l'ouverture de l'écran et la présence
  des statistiques ; « Continuer » rend la main sans erreur.

---

## 6. P2 (cadrage court, à spécifier avant lancement)

- **F11 Feuillage.** Cartes alpha croisées par canopée (4 à 8 quads par
  arbre) avec l'atlas CC0 déjà en place, `ALPHA_TO_COVERAGE` (leçon v1),
  imposteurs à 2 quads au-delà de 250 m. Risque principal : le sur-dessin
  (overdraw) en forêt ; budget à mesurer avant de généraliser.
- **F12 Accessibilité.** Remap des touches dans le menu pause (l'InputMap est
  déjà installé par code, il suffit de le rendre éditable et persisté),
  formes en plus des couleurs sur la carte, sous-titres optionnels des cris
  allemands (« Alarme ! », « Il est là ! ») pour les joueurs sourds.
- **F13 Sauvegardes.** `SaveManager` sait déjà nommer des campagnes ; il
  manque l'UI (3 emplacements) et un mode « Fer » (mort = fin de campagne).
- **F14 Localisation.** Extraire les chaînes en dur vers une table ; hors
  d'atteinte tant que F1 à F10 bougent l'UI chaque semaine.
- **F15 Véhicule.** Kübelwagen pilotable (couche `VEHICLE` réservée depuis
  v1). À ne lancer qu'après F5/F6 : un véhicule casse l'infiltration et
  l'équilibrage des distances si le reste n'est pas stabilisé.

---

## 7. Exigences transverses

1. **Contrat d'abord.** Toute signature nouvelle ou modifiée passe par
   `docs/CONTRACTS.md` avant le code, même en travaillant seul.
2. **Compatibilité des sauvegardes.** Tout `from_dict` tolère les clés
   absentes (une sauvegarde v1 se charge en v2 sans perte) ; on n'enlève ni
   ne renumérote jamais un id persisté (armes, sites, objectifs).
3. **Budgets intangibles** sauf décision explicite : 60 soldats, 14 escouades,
   1800 instances par tuile, pire frame < 16 ms.
4. **Chaque fonctionnalité livre ses vérifications** : suite unitaire si le
   coeur est pur, extension de la sonde sinon, et au moins une capture
   `--shot` si l'effet est visuel.
5. **Zéro nouvelle dépendance.** Godot 4.7.1 nu, assets CC0 uniquement, repli
   procédural obligatoire pour tout nouvel asset.

## 8. Métriques de succès

| Métrique | v1 | Cible v2 |
|---|---|---|
| Promesses UI non tenues | 2 | 0 |
| Démarrage (prime de spawn) | 2.3 à 3.2 s | < 1.5 s |
| Pire frame en streaming | 13.3 ms | < 16 ms (inchangé) |
| Vérifications automatiques | 6979 | > 7600, 0 échec |
| Capture silencieuse possible | non mesurable | oui, créditée |
| Trajet subi maximal | ~15 min à pied | < 90 s |

## 9. Jalons proposés

1. **Lot A « Dettes »** : F1, F2, F3, F4. Critère de sortie : les trois dettes
   fermées, démarrage mesuré < 1.5 s, suites vertes.
2. **Lot B « Maquis »** : F5, F6, F8. Critère : une capture silencieuse
   complète réalisée et créditée en partie réelle ; une contre-attaque
   vaincue et une subie, sauvegardées et rechargées.
3. **Lot C « Frères d'armes »** : F7, F9, F10. Critère : campagne terminée
   avec 2 compagnons, débriefing affiché, voyage rapide utilisé sans chute
   sous le terrain.
4. **Lot D « Horizon »** (P2, à re-prioriser après le lot C).

Chaque lot se termine par : suites complètes, sonde, série de captures, et une
passe de revue adversariale sur les modules touchés (méthode v1, qui a trouvé
les 9 défauts confirmés).

## 10. Risques et questions ouvertes

| Risque | Impact | Mitigation |
|---|---|---|
| F6 état « contesté » complexifie War | corruption de sauvegarde | état séparé de `captured`, jamais de retrait d'un secteur capturé |
| F9 compagnons dans les portes étroites (1.6 m) | blocages visibles | réutiliser l'anti-blocage soldat + téléport doux à 8 m du joueur |
| F2 musique synthétisée « cheap » | casse l'ambiance | parti pris minimaliste : percussions et nappes, pas de mélodie exposée |
| F11 overdraw du feuillage | chute de FPS en forêt | prototype sur une tuile, mesure, puis décision |
| Ajout d'ids d'armes | vieille sauvegarde avec id inconnu | `from_dict` borne l'id et retombe sur le Garand |

Questions à trancher par le propriétaire du produit :

1. **Ton narratif** : l'uchronie assumée (une poche libérée en 1942) est-elle
   le cadre voulu, ou faut-il re-dater la campagne en 1944 pour coller au
   débarquement historique ? (Impact : textes de mission uniquement.)
2. **F6** : un secteur contesté qui retombe est-il trop punitif ? Alternative
   plus douce : la contre-attaque vaincue est purement un événement de combat,
   sans état de carte.
3. **F15 véhicule** : souhaité à terme ou hors périmètre définitif ?

---

*Rédigé à partir du code réel du dépôt (v1, 30 577 lignes, suites vertes) et
des mesures effectuées les 2026-08-22 et 2026-08-23.*
