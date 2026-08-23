# Textures

Toutes les textures de ce dossier viennent de **Poly Haven** (https://polyhaven.com)
et sont publiees sous licence **CC0 1.0 Universal** (domaine public). Aucune
attribution n'est juridiquement exigee ; elle est donnee ici par courtoisie.

Chaque matériau est fourni en 1024 x 1024 JPEG, en trois cartes :

| Suffixe | Contenu | Usage Godot |
|---|---|---|
| `_albedo` | couleur de base | `albedo_texture` |
| `_normal` | normales OpenGL (`nor_gl`) | `normal_texture` |
| `_arm` | AO (rouge), rugosite (vert), metal (bleu) | `ao_texture` / `roughness_texture` / `metallic_texture` par canal |

| Fichier | Source Poly Haven |
|---|---|
| `grass_*` | aerial_grass_rock |
| `dirt_*` | dirt_floor |
| `road_*` | cobblestone_03 |
| `stone_*` | old_stone_wall |
| `plaster_*` | damaged_plaster |
| `wood_*` | brown_planks_03 |
| `roof_tile_*` | clay_roof_tiles_02 |
| `roof_slate_*` | roof_slates_02 |
| `concrete_*` | rough_concrete |
| `metal_*` | metal_plate |
| `rust_*` | rust_coarse_01 |
| `bark_*` | bark_brown_02 |
| `sand_*` | coast_sand_01 |

Le feuillage, le ble et l'herbe haute restent **procéduraux** : ils ont besoin
d'un canal alpha decoupe (alpha scissor) que ces textures opaques ne fournissent
pas.

## Atlas de brins (alpha)

`blade_color.png` et `blade_opacity.png` viennent d'**ambientCG** (Foliage001),
egalement en **CC0**. Ils sont fusionnes en une seule image RGBA au chargement,
puis recadres sur un brin unique : voir `Tex._blade_texture()`. Un atlas ne peut
pas etre utilise tel quel ici, car les quads de brin echantillonnent la totalite
de l'UV et afficheraient les neuf brins sur une seule lame.
