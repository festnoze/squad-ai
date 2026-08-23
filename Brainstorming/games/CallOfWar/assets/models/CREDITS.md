# Modèles de personnages

Les deux fichiers `.glb` de ce dossier sont les seuls maillages binaires du
projet : tout le reste de la géométrie est généré par `Meshes`. Ils sont chargés
par `CharacterModels`, qui retombe sur les soldats en boîtes si le dossier est
absent.

| Fichier | Contenu | Auteur | Licence | Source |
|---|---|---|---|---|
| `soldier.glb` | soldat lowpoly rigge, 24 animations | Quaternius | **CC0 1.0** | https://poly.pizza/m/Btfn3G5Xv4 |
| `zombie.glb` | zombie lowpoly rigge, 5 animations | Quaternius | **CC-BY 3.0** | https://poly.pizza/m/jkrEvQZb8J |

## Attribution

`soldier.glb` est en CC0 (domaine public) : aucune attribution n'est exigée.

`zombie.glb` est en **CC-BY 3.0**, qui impose de citer l'auteur. La mention
ci-dessous doit donc rester visible dans le jeu ou dans sa documentation :

> Modèle « Animated Zombie » par Quaternius (https://quaternius.com),
> distribué sous licence Creative Commons Attribution 3.0
> (https://creativecommons.org/licenses/by/3.0/).

## Caractéristiques mesurées

Ces chiffres sont ceux qu'utilise `CharacterModels._SPECIES`. Ils viennent d'une
mesure, pas de la fiche produit : la boîte englobante que Godot expose pour un
maillage skinné est stockée en espace de liaison et vaut 8,1 m pour le zombie,
soit plus de quatre metres de trop.

| | `soldier.glb` | `zombie.glb` |
|---|---|---|
| Hauteur au repos | 1,854 m | 6,933 m |
| Facteur appliqué (cible 1,80 m) | 0,971 | 0,260 |
| Orientation native | +Z (retournee de 180° par le nœud `Rig`) | +Z (idem) |
| Squelette | 62 os, nommage `Wrist.R` | 41 os, nommage Mixamo `RightHand` |
| Triangles | 7 752 | 2 116 |
| Os de la main portant l'arme | `Wrist.R` | `RightHand` |

## Lacunes connues

- Le zombie ne fournit **ni animation de mort ni animation d'impact**. `Soldier`
  le détecte via `CharacterAnim.has()` et rebascule sur la chute procédurale.
- Aucun des deux rigs n'a de pose accroupie. Le corps est enfonce de 0,42 m
  comme le faisait le soldat en boîtes, ce qui garde la tête à peu près sur la
  ligne de tir à la tête mais enterre les pieds.
- Les deux modèles sont d'époque moderne, pas 39-45 : aucun modèle WWII rigge
  n'existe en licence libre. Les casques et le gilet tactique sont donc
  anachroniques pour la Normandie 1942.
