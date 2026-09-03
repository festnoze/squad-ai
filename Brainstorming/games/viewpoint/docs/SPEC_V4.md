# SPEC v4 - Le remplacement total

Contrat d'implementation. 2026-08-31. Ce document fait foi : toute ambiguite
se resout en le suivant a la lettre. Regles d'ecriture du projet : texte
joueur en francais, code et commentaires en anglais, jamais de tiret
cadratin, indentation GDScript en TABULATIONS.

Vision : la photo devient ce qu'elle est dans Viewfinder. Une photo est
TOUJOURS la representation 2D d'un espace 3D : des blocs 3D + un fond 2D
peint. La poser REMPLACE tout ce qui est dans sa perspective (jusqu'a la
distance du fond) par son contenu. L'appareil photographie TOUT ce qui entre
dans le cadre, y compris le vide : poser une photo de ciel PERCE le monde.
On ne previsualise plus le resultat en 3D : on leve la photo (image 2D), on
la tourne, et on ne decouvre le resultat qu'a la pose.

## 1. Interaction (src/player/player.gd, src/core/game_state.gd)

- `Player.INTERACT_RANGE` passe de 3.4 a **1.7**.
- **Reposer une pile avec E** : quand E est presse SANS cible d'interaction
  et que `Game.carried_batteries > 0` : appeler `Game.drop_battery()` et, si
  true, instancier une `Battery` dans `level_root` a
  `player.global_position + forward_plat * 1.2 + Vector3(0, 0.05, 0)`
  (forward_plat = -basis.z du corps, aplati, normalise).
  - `Game.drop_battery() -> bool` : si `carried_batteries <= 0` retourne
    false ; sinon decremente, emet `batteries_changed`, retourne true.
  - Le player recoit `level_root` dans `setup()` (le stocker en membre).
  - `interact_prompt` quand aucune cible et `carried > 0` :
    `"E : reposer une pile"`.

## 2. Groupes et blocs (erasable_block.gd, level_builder.gd, photo_content.gd)

Tout bloc-boite du monde devient un `ErasableBlock` (decoupable) :

- `ErasableBlock.create(size: Vector3, color: String, emissive := 0.0,
  extra_groups: PackedStringArray = PackedStringArray()) -> ErasableBlock`.
  `_ready()` : groupe **"carvable"** + chaque groupe de `extra_groups` ;
  materiau `Materials.solid(color_key, emissive)`. Les fragments issus de
  `carve_with_frustum` recreent des blocs avec les MEMES color/emissive/
  extra_groups (stocker ces champs en membres).
- `LevelBuilder` :
  - plateformes -> `ErasableBlock.create(size, "platform", 0.0, ["platform"])`
    a `pos` ; la jupe (skirt) devient un MeshInstance3D ENFANT du bloc (elle
    disparait avec lui ; les fragments n'ont pas de jupe, assume).
  - decors -> `ErasableBlock.create(size, color)` (plus de `_add_block`).
  - lavande (`erasables`) -> `ErasableBlock.create(size, "erasable", 0.25,
    ["erasable"])`. Le groupe "erasable" ne sert plus qu'a la lisibilite et
    aux tests (marqueur lavande).
  - cages : le corps rejoint le groupe **"breakable"** (plus jamais
    "erasable"). TOUTES les cages, permanentes comprises, sont cassables.
    Garder la difference visuelle lavande/sombre (indice de lore, plus de
    regle differente).
- `PhotoContent` solide : chaque primitive box NON loose (voir section 6)
  devient un `ErasableBlock.create(prim.size, prim.color)` positionne au
  centre de la primitive (donc le contenu pose est lui-meme remplacable).
  Le mur de fond (backdrop) solide devient un ErasableBlock mince
  (size.x, size.y, 0.2). La rampe invisible des escaliers devient un
  ErasableBlock (la decoupe echantillonne en espace local : la rotation est
  geree). Les cylindres restent des StaticBody3D ordinaires.

## 3. Remplacement a la pose (photo_placer.gd)

`place()` : `depth = def.erase_depth` (toujours = profondeur du fond,
section 4). Deux passes AVANT l'instanciation :

1. groupe "carvable" : `carve_with_frustum(anchor, fov, aspect, depth)` sur
   chaque bloc (comportement de decoupe inchange).
2. groupe "breakable" : si le CENTRE (`global_position` du corps, qui est
   deja le centre volumique de la cage) tombe dans le frustum
   (`PhotoMath.point_in_frustum`, near 0.0, far depth) -> `queue_free()`.

Ne sont JAMAIS remplaces : teleporteur, piles, objets photo, appareil,
joueur. Une photo VIDE (props vides, fond seul) fait donc exactement ce que
demande le titre : elle perce murs, sols et cages, et peint son fond.

## 4. Toute photo a un fond 2D peint (photo_defs.gd)

Chaque definition du catalogue recoit un `backdrop` non vide et
`erase_depth == backdrop.depth` (la regle du scelle devient universelle) :

| id | backdrop.depth | top / bottom |
|---|---|---|
| passerelle | 9.5 | sky_top / sky_horizon |
| pile | 8.0 (inchange) | backdrop_top / backdrop_bottom |
| escalier | 9.0 | sky_top / sky_horizon |
| porte | 6.2 (mur scelle inchange a 6.0, fond peint juste derriere) | sky_top / sky_horizon |
| console | 6.0 | sky_top / sky_horizon |
| corniche | 6.0 | sky_top / sky_horizon |
| caisse | 5.0 | sky_top / sky_horizon |
| coffret | 6.0 | backdrop_top / backdrop_bottom |

Le test `test_porte_seal` reste valable (mur a 6.0, decoupe <= 6.2).

## 5. La pellicule capture TOUT (photo_capture.gd, player.gd)

- Candidats de `capture()` :
  - tous les `ErasableBlock` du groupe "carvable" (pos = global_position,
    size = block_size, color = color_key) ;
  - tous les corps du groupe "breakable" (cages) : prop box, pos = centre,
    size = taille de la cage (stocker `cage_size` en meta ou en membre du
    corps a la construction : `body.set_meta("cage_size", size)`),
    color "battery_tip" ;
  - toutes les piles (kind battery, pos = base).
- Filtre frustum inchange (near 0.5, far CAPTURE_DEPTH 12). Trier les props
  par profondeur croissante et PLAFONNER a 32 props.
- Le def retourne TOUJOURS quelque chose : props eventuellement vides, et
  toujours `"backdrop": {"depth": 12.0, "top": "sky_top",
  "bottom": "sky_horizon"}`, `"erase_depth": 12.0`. `capture()` ne retourne
  plus jamais `{}`.
- `Player.capture_photo()` : consomme TOUJOURS un film (si mains vides et
  film > 0). La photo vide est un outil, pas un echec. Supprimer le signal
  `capture_failed` et son cablage dans main.gd (toast comprise).
- Prop box capture : marquer `"loose": true` ssi size.x <= 1.6 et
  size.y <= 1.6 et size.z <= 1.6 (caisses et petits objets tombent, murs,
  planches de 4 m et pans de plateforme restent solidaires).

## 6. Physique des objets libres (photo_content.gd, battery.gd, photo_defs.gd)

- Prop box avec `"loose": true` -> a la pose solide : `RigidBody3D`
  (collision_layer = Layers.WORLD, collision_mask = Layers.WORLD,
  mass = clampf(volume * 2.0, 1.0, 10.0)) + BoxShape + MeshInstance. Pose a
  l'envers ou dans le vide : il tombe, c'est le but.
- Prop battery -> TOUJOURS physique a la pose : `RigidBody3D` (memes
  couches, mass 1.5, BoxShape 0.36 x 0.72 x 0.36) portant la `Battery` en
  enfant a (0, -0.36, 0).
- `Battery.interact()` : si `get_parent() is RigidBody3D`, liberer le parent
  au lieu de soi-meme (sinon la coquille physique vide reste).
- Catalogue : le prop box de "caisse" recoit `"loose": true`. Le socle de
  "pile" et de "coffret" RESTE statique (pos exacte voulue). La dalle de
  console/corniche RESTE statique (les retournements a 180 degres sont des
  plateformes voulues). L'expansion (`expand_prop`) PROPAGE la cle "loose"
  des props box vers leurs primitives.

## 7. Plus de fantome 3D (photo_placer.gd, hud.gd, main.gd)

- `hold()` ne cree PLUS de fantome (supprimer la creation ; garder le champ
  `_ghost` inutile est interdit : nettoyer). `raised` et `roll_steps`
  restent. `raise_toggle()` ne gere plus de visibilite de fantome.
- Le HUD affiche l'image levee TOURNEE : `set_photo_view(texture, roll_steps)`
  applique `rotation = roll_steps * PI / 2` au TextureRect avec
  `pivot_offset = size / 2` (pivot au centre, a poser APRES la taille).
- Panneau photo tenue : ajouter une mini vignette (TextureRect 110 x 110,
  STRETCH_KEEP_ASPECT) au-dessus du titre, alimentee par main via
  `hud.set_held(title, texture)` (texture null quand rien).
- main._process passe `player.placer.roll_steps` a `set_photo_view` et la
  texture `PhotoSnaps.get_texture(held_id)` a `set_held`.
- Textes : panneau tenu : "Clic gauche : poser   Clic droit : lever
  Molette : pivoter   F : reposer". Menu titre : remplacer la ligne clic
  droit par "Clic droit lever la photo (molette : la tourner)". PRD section
  6 : mise a jour des lignes clic droit / molette / E (portee 1.7 m,
  reposer une pile).

## 8. Niveaux (level_defs.gd, docs/LEVELS_V2.md) - agent niveaux

Reviser LES 20 NIVEAUX pour les nouvelles regles, et AUGMENTER la
difficulte globale. Realites nouvelles a respecter :

- Poser une photo decoupe AUSSI les plateformes et plante toujours son fond
  peint (mur) a `backdrop.depth`. Les niveaux doivent survivre aux poses
  legitimes (le teleporteur est indestructible mais peut se retrouver
  derriere un mur peint : laisser du contournement, plateformes un peu plus
  larges la ou la pose est obligatoire).
- Toute cage est cassable par n'importe quelle pose qui attrape son centre
  (y compris une photo vide). Les puzzles "cage" deviennent des puzzles
  d'economie (quelle photo sacrifier) ou de portee (cage hors des 12 m).
- La photo vide (appareil, cadrer le ciel) est un outil de percage etendu :
  au moins UN niveau doit l'exiger explicitement (casser un mur ou une cage
  sans photo classique disponible).
- Physique : caisses posees et piles posees tombent ; une pose a l'envers
  (roll 180) fait chuter les objets libres. Au moins UN niveau doit exploiter
  la chute (ex : faire tomber une pile de l'autre cote d'une grille en la
  posant en hauteur, ou une caisse a faire tomber dans une fosse pour en
  faire une marche).
- Portee d'interaction reduite a 1.7 m : les piles doivent etre atteignables
  de pres ; plus de ramassage a travers une vitrine profonde (adapter la
  vitrine des niveaux 12/15 : profondeur de niche <= 1.2 m).
- La previsualisation 3D n'existe plus : les poses de precision doivent
  avoir des reperes visuels au sol (dalles decoratives, teintes) la ou
  c'etait critique.
- Budget cinematique inchange (LEVELS_V2 section 2).
- Solvabilite : le test compte monde + photos recursif + pellicule (si
  appareil ET piles presentes). Chaque niveau doit rester couvert.
- Mettre a jour la section 4 et 4 bis de docs/LEVELS_V2.md (design des
  niveaux revises) et ajouter une section 1.7 decrivant remplacement total,
  photo vide et physique.

## 9. Tests (agent tests) - etat attendu

- `test_photo_defs` : toutes les defs ont un backdrop non vide ;
  `erase_depth == backdrop.depth` pour TOUTES ; caisse a un prop loose ;
  l'expansion propage "loose".
- `test_photo_capture` : la capture inclut les blocs non lavande ; une
  capture vide retourne un def valide (props [], backdrop 12) ; le plafond
  de 32 props ; la regle loose (<= 1.6 sur les trois axes).
- `test_game_state` : `drop_battery` (borne a zero, decremente, signal).
- `test_level_defs` : s'adapte aux nouveaux defs (compte 20 inchange).
- `smoke_probe` : adapter les groupes (cages dans "breakable", lavande
  toujours dans "erasable", plateformes dans "carvable") ; supprimer les
  verifications de fantome ; la capture du ciel REUSSIT et consomme un
  film ; verifier `drop_battery` via E-logique (appel direct
  Game.drop_battery + spawn) ; verifier la chute d'une caisse posee en
  hauteur (placer "caisse" avec roll 180 depuis le sol, attendre 60 frames,
  la caisse doit etre SOUS y de pose initiale) ; verifier qu'une photo vide
  posee face a une cage la casse ; garder toutes les verifications
  existantes qui restent vraies, adapter les autres. Les tests doivent etre
  VERTS (unitaires ET smoke) a la fin.

## 10. Interdits

- Ne pas toucher a : project.godot, main.tscn, run.bat, la regle du scelle,
  PhotoSnaps (sauf cablage main), le menu de selection de niveau, la
  progression persistee.
- Ne jamais introduire de tiret cadratin. Tabs en GDScript. Pas de
  commentaire en francais dans le code.
