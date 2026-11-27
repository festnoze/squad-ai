# Contours des niveaux et carte d’Europe

Le fichier `Assets/Resources/Europe/countries.json` contient 46 pays. Le périmètre suit les États de la région Europe de l’ONU M49, avec la Turquie, Chypre et le Kosovo ajoutés et la Russie retirée. Il comprend le Royaume-Uni avec l’Irlande du Nord et les six micro-États d’Andorre, du Liechtenstein, de Malte, de Monaco, de Saint-Marin et du Vatican. Les dépendances séparées, le Caucase et le Kazakhstan sont hors périmètre.

La carte garde les parties européennes continentales et les îles régionales retenues par le modèle, ainsi que toute la Turquie et l’île de Chypre. Le Portugal couvre sa partie continentale. L’Espagne inclut les Baléares. La France inclut la Corse. La Norvège inclut ses îles côtières. Le fond ne représente pas les pays ni les territoires hors périmètre.

## Sources

- [Natural Earth Admin 0 à l’échelle 1:10 millions](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/), couches `ne_10m_admin_0_map_units` et `ne_10m_admin_0_countries_ukr`, version vectorielle [v5.1.2](https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2/geojson). [Domaine public](https://www.naturalearthdata.com/about/terms-of-use/).
- [Classification géographique M49 de l’ONU](https://unstats.un.org/unsd/methodology/m49/overview/) pour établir le périmètre de base.

La variante ukrainienne de Natural Earth inclut la Crimée dans le contour de l’Ukraine. Pour le visuel d’arène, Chypre est une silhouette insulaire unique qui fusionne les unités cartographiques de l’île. Les contours sont des données cartographiques généralisées destinées au jeu.

## Format Unity

| Champ | Signification |
| --- | --- |
| `code`, `name` | Identifiant alpha-2, nom français. `GB` désigne le Royaume-Uni et `XK` le Kosovo. |
| `parts` | Parties cartographiques, triées par surface décroissante. Le seuil de 20 km² ne concerne que les parties secondaires. |
| `outer`, `holes[].points` | Anneaux ouverts, CCW à l’extérieur et CW pour les trous. `x` est orienté vers l’est et `y` vers le nord, en kilomètres. |
| `vertices`, `triangles` | Sommet et indices de la face supérieure pour triangulation contrainte avec trous. Triplets CCW dans le plan XY. |
| `label` | Point situé loin des bords dans la plus grande partie cartographique. |
| `level` | Contour continu de la partie principale, avec enclaves comblées et îles séparées écartées. Au plus 128 sommets, centré sur la boîte d’origine et normalisé sur l’axe le plus long. |
| `levelCenter`, `levelRadius` | Centre et rayon approximatifs du plus grand disque inscrit, dans le même repère que `level`. |

Pour la carte, la projection EPSG:3035 conserve les proportions de surface. Les coordonnées sont recentrées à `(4 321 000 m, 3 000 000 m)`. Dans Unity, les coordonnées horizontales peuvent être converties en XZ en adaptant l’ordre des triangles à la normale de face souhaitée.

## Génération et contrôles

Le générateur télécharge les deux sources dans un répertoire de cache local et vérifie leur SHA-256. Il assemble les sous-unités, projette les coordonnées en kilomètres, partage exactement les arêtes des frontières communes et applique une simplification conjointe. Les anneaux cartographiques sont sérialisés avec une précision d’un mètre.

```powershell
py -3.13 -m pip install shapely==2.1.2 pyproj==3.7.2 numpy==2.5.5
py -3.13 tools/generate_europe.py --cache-dir $env:TEMP
```

Les données livrées comportent 46 niveaux, 375 polygones cartographiques et 33 756 triangles. Les contrôles ont vérifié la validité de la couverture après sérialisation, le sens et la surface des triangles, les centres intérieurs des 46 niveaux et les frontières communes, dont le Royaume-Uni avec l’Irlande et l’Italie avec le Vatican.

## Utilisation dans le jeu

Dans le menu principal, ouvrir **Pays**. La carte 3D se construit à partir des parties cartographiques et du maillage de chaque pays. Toucher un pays sur la carte ou utiliser les flèches, qui donnent aussi accès aux micro-États. Le pays actif se soulève et porte un drapeau animé sur un mât. Les [textures des drapeaux](europe/FLAGS.md) gardent leurs proportions d’origine.

**Jouer ce pays** lance la manche sur le contour continu simplifié, à une échelle comparable entre pays. L’arène tient compte des concavités pour les déplacements, les départs des quatre joueurs, le calcul du territoire et l’affichage des frontières dans les trois biomes. **Rejouer** reprend le même contour. **Jouer** dans le menu principal lance l’arène classique.
