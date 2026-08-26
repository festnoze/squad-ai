# Crédits des assets de GOAL

Les assets externes listés ci-dessous sont en **CC0 1.0 Universal** (domaine
public). **Aucune attribution n'est juridiquement exigée.** Les mentions sont
données par courtoisie et pour la traçabilité. Les textures de tenue et de
visage ont été générées spécialement pour ce jeu et sont identifiées séparément.

**Aucun asset de ce dossier ne porte de blason de club, de maillot officiel, de
logo de sponsor réel ni de ressemblance avec un joueur réel.** Le joueur est un
maillage humain générique et les marques `NOVA` et `ASTRA` des tenues sont
fictives. Les panneaux publicitaires restent des blocs abstraits générés par
`Tex`.

---

## Personnage

| Fichier | Contenu | Auteur | Licence | Source |
|---|---|---|---|---|
| `models/player.glb` | humain riggé, 31 370 triangles, 163 os, tenue de football découpée en pièces | MakeHuman Community | **CC0 1.0** | https://github.com/makehumancommunity/makehuman |
| `models/player_uv_regions.png` | carte des régions de l'atlas UV du corps | dérivé du même maillage | **CC0 1.0** | idem |

`player.glb` est **dérivé** de trois fichiers du dépôt MakeHuman, tous passés en
CC0 en septembre 2020 :

- `makehuman/data/3dobjs/base.obj` (maillage du corps et coques d'habillage)
- `makehuman/data/rigs/default.mhskel` (squelette de 163 os)
- `makehuman/data/rigs/default_weights.mhw` (poids de skinning)

Mention de courtoisie :

> Maillage humain et squelette issus de **MakeHuman**
> (https://www.makehumancommunity.org), publiés sous **CC0 1.0**.
> Détenteurs des droits au moment du passage en CC0 : Data Collection AB,
> Joel Palmius, Jonas Hauquier.

Le fichier `.glb` n'est pas le fichier d'origine : le corps a été extrait des
coques auxiliaires, triangulé, mis à l'échelle en mètres, gréé au format glTF et
découpé en sept primitives. La licence CC0 autorise explicitement ces
transformations.

Le fichier compte **31 370 triangles** et il est livré tel quel. Les frontières
entre pièces qu'il porte sont dentelées et asymétriques, et le jeu ne les
utilise pas : `src/world/character_models.gd` **recoupe** la tenue au chargement
sur des plans propres, ce qui porte le maillage affiché à **31 968 triangles**.
Le fichier lui-même n'est jamais réécrit et sa licence CC0 est inchangée.

---

## Textures

### Textures originales du jeu

| Fichier | Contenu | Provenance |
|---|---|---|
| `textures/kits/outfield_kit_albedo.png` | maillot et short bleu, sponsor fictif `NOVA`, numéro 9 | généré spécialement pour GOAL avec OpenAI ImageGen |
| `textures/kits/outfield_front_albedo.png` | devant du maillot bleu `NOVA`, sans numéro | variante générée spécialement pour GOAL avec OpenAI ImageGen |
| `textures/kits/keeper_kit_albedo.png` | tenue de gardien orange/noire, sponsor fictif `ASTRA`, numéro 1 | généré spécialement pour GOAL avec OpenAI ImageGen |
| `textures/kits/keeper_front_albedo.png` | devant du maillot orange `ASTRA`, sans numéro | variante générée spécialement pour GOAL avec OpenAI ImageGen |
| `textures/characters/keeper_skin_albedo.png` | visage et peau d'un gardien adulte fictif | généré spécialement pour GOAL avec OpenAI ImageGen |
| `textures/crowd/stadium_spectators_atlas.png` | atlas transparent de 12 supporters adultes fictifs pour les tribunes | généré spécialement pour GOAL avec OpenAI ImageGen |
| `textures/crowd/stadium_spectators_atlas_02.png` | second atlas transparent de 12 supporters adultes fictifs | généré spécialement pour GOAL avec OpenAI ImageGen |
| `textures/seats/stadium_seat_albedo.png` | siège de stade bleu photoréaliste détouré | généré spécialement pour GOAL avec OpenAI ImageGen |

Ces images suivent la carte UV du modèle. Les tenues ne reproduisent aucun
maillot, écusson ou sponsor réel, et le visage ne représente aucune personne
réelle.

### Poly Haven (https://polyhaven.com) - CC0 1.0

| Préfixe local | Asset Poly Haven | Auteurs |
|---|---|---|
| `turf_worn_*` | `sparse_grass` | Amal Kumar |
| `concrete_*` | `concrete_wall_008` | Dario Barresi (traitement), Charlotte Baglioni (photographie) |
| `concrete_floor_*` | `concrete_floor_02` | Rob Tuytel |
| `metal_painted_*` | `blue_metal_plate` | Rob Tuytel |
| `cladding_*` | `box_profile_metal_sheet` | Amal Kumar |

### ambientCG (https://ambientcg.com) - CC0 1.0

| Préfixe local | Asset ambientCG | Auteur |
|---|---|---|
| `turf_*` | `Grass005` | Lennart Demes / ambientCG |
| `turf_stripe_*` | `Grass008` | Lennart Demes / ambientCG |
| `seat_plastic_*` | `Plastic010` | Lennart Demes / ambientCG |
| `net_*` | `Net001A` | Lennart Demes / ambientCG |
| `steel_*` | `Metal038` | Lennart Demes / ambientCG |

Mention de courtoisie :

> Textures **Poly Haven** (https://polyhaven.com) et **ambientCG**
> (https://ambientcg.com), publiées sous **CC0 1.0 Universal**.

Les jeux ambientCG ont été **recombinés** : les cartes `_arm.jpg` sont fabriquées
ici en empilant occlusion ambiante, rugosité et métallicité dans les canaux
rouge, vert et bleu. Le cordage de `net_albedo.png` a été **désaturé et
éclairci** vers un blanc de filet de but ; l'opacité d'origine est conservée
telle quelle dans le canal alpha.

---

## Ce que le dépôt ne contient volontairement pas

Aucun modèle sous **Mixamo**, **Renderpeople**, **Ready Player Me**, **CGTrader**,
**TurboSquid** ni **Free3D** : leurs conditions autorisent l'usage dans un jeu
mais pas la redistribution du fichier dans un dépôt public, ce qui est exactement
ce que ferait ce dossier. Voir le rapport d'acquisition pour le détail.
