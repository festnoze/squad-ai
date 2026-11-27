# Drapeaux des niveaux européens

Le jeu utilise 46 textures de drapeaux nationaux. La série suit les pays retenus pour la carte, dont Chypre, le Kosovo, le Royaume-Uni et la Turquie. `XK` est le code employé pour le Kosovo dans ce projet. `GB` est le code ISO 3166-1 alpha-2 du Royaume-Uni.

## Assets Unity

Les fichiers `Assets/Resources/EuropeFlags/<code>.png` importent des textures sRGB opaques de 320 px de large, avec mipmaps et échantillonnage Clamp. Ils reprennent les proportions de la version d’origine, à l’arrondi au pixel près. Les contours, couleurs et armoiries sont repris des PNG sans redimensionnement ni retouche.

Charger la texture via `Resources.Load<Texture2D>("EuropeFlags/" + code)`. Appliquer les UV 0–1 à un maillage de tissu et fixer le rapport largeur/hauteur du maillage à `(float)texture.width / texture.height`. Le bord gauche de la texture correspond à la hampe. L’animation relève du maillage ou du matériau de tissu.

## Provenance

PNGs fournis par [Flagpedia](https://flagpedia.net/about) via son [CDN, option w320 au format d’origine](https://flagpedia.net/download/api). Flagpedia se fonde sur les fichiers vectoriels de Wikimedia Commons et annonce ses PNG comme relevant du domaine public. Les liens ci-dessous pointent vers les images effectivement utilisées.

| Code | Pays | Dimensions (px) | Source |
| --- | --- | --- | --- |
| AD | Andorre | 320 × 224 | [PNG](https://flagcdn.com/w320/ad.png) |
| AL | Albanie | 320 × 229 | [PNG](https://flagcdn.com/w320/al.png) |
| AT | Autriche | 320 × 213 | [PNG](https://flagcdn.com/w320/at.png) |
| BA | Bosnie-Herzégovine | 320 × 160 | [PNG](https://flagcdn.com/w320/ba.png) |
| BE | Belgique | 320 × 277 | [PNG](https://flagcdn.com/w320/be.png) |
| BG | Bulgarie | 320 × 192 | [PNG](https://flagcdn.com/w320/bg.png) |
| BY | Biélorussie | 320 × 160 | [PNG](https://flagcdn.com/w320/by.png) |
| CH | Suisse | 320 × 320 | [PNG](https://flagcdn.com/w320/ch.png) |
| CY | Chypre | 320 × 213 | [PNG](https://flagcdn.com/w320/cy.png) |
| CZ | Tchéquie | 320 × 213 | [PNG](https://flagcdn.com/w320/cz.png) |
| DE | Allemagne | 320 × 192 | [PNG](https://flagcdn.com/w320/de.png) |
| DK | Danemark | 320 × 242 | [PNG](https://flagcdn.com/w320/dk.png) |
| EE | Estonie | 320 × 204 | [PNG](https://flagcdn.com/w320/ee.png) |
| ES | Espagne | 320 × 213 | [PNG](https://flagcdn.com/w320/es.png) |
| FI | Finlande | 320 × 196 | [PNG](https://flagcdn.com/w320/fi.png) |
| FR | France | 320 × 213 | [PNG](https://flagcdn.com/w320/fr.png) |
| GB | Royaume-Uni | 320 × 160 | [PNG](https://flagcdn.com/w320/gb.png) |
| GR | Grèce | 320 × 213 | [PNG](https://flagcdn.com/w320/gr.png) |
| HR | Croatie | 320 × 160 | [PNG](https://flagcdn.com/w320/hr.png) |
| HU | Hongrie | 320 × 160 | [PNG](https://flagcdn.com/w320/hu.png) |
| IE | Irlande | 320 × 160 | [PNG](https://flagcdn.com/w320/ie.png) |
| IS | Islande | 320 × 230 | [PNG](https://flagcdn.com/w320/is.png) |
| IT | Italie | 320 × 213 | [PNG](https://flagcdn.com/w320/it.png) |
| LI | Liechtenstein | 320 × 192 | [PNG](https://flagcdn.com/w320/li.png) |
| LT | Lituanie | 320 × 192 | [PNG](https://flagcdn.com/w320/lt.png) |
| LU | Luxembourg | 320 × 192 | [PNG](https://flagcdn.com/w320/lu.png) |
| LV | Lettonie | 320 × 160 | [PNG](https://flagcdn.com/w320/lv.png) |
| MC | Monaco | 320 × 256 | [PNG](https://flagcdn.com/w320/mc.png) |
| MD | Moldavie | 320 × 160 | [PNG](https://flagcdn.com/w320/md.png) |
| ME | Monténégro | 320 × 160 | [PNG](https://flagcdn.com/w320/me.png) |
| MK | Macédoine du Nord | 320 × 160 | [PNG](https://flagcdn.com/w320/mk.png) |
| MT | Malte | 320 × 213 | [PNG](https://flagcdn.com/w320/mt.png) |
| NL | Pays-Bas | 320 × 213 | [PNG](https://flagcdn.com/w320/nl.png) |
| NO | Norvège | 320 × 233 | [PNG](https://flagcdn.com/w320/no.png) |
| PL | Pologne | 320 × 200 | [PNG](https://flagcdn.com/w320/pl.png) |
| PT | Portugal | 320 × 213 | [PNG](https://flagcdn.com/w320/pt.png) |
| RO | Roumanie | 320 × 213 | [PNG](https://flagcdn.com/w320/ro.png) |
| RS | Serbie | 320 × 213 | [PNG](https://flagcdn.com/w320/rs.png) |
| SE | Suède | 320 × 200 | [PNG](https://flagcdn.com/w320/se.png) |
| SI | Slovénie | 320 × 160 | [PNG](https://flagcdn.com/w320/si.png) |
| SK | Slovaquie | 320 × 213 | [PNG](https://flagcdn.com/w320/sk.png) |
| SM | Saint-Marin | 320 × 240 | [PNG](https://flagcdn.com/w320/sm.png) |
| TR | Turquie | 320 × 213 | [PNG](https://flagcdn.com/w320/tr.png) |
| UA | Ukraine | 320 × 213 | [PNG](https://flagcdn.com/w320/ua.png) |
| VA | Vatican | 320 × 320 | [PNG](https://flagcdn.com/w320/va.png) |
| XK | Kosovo | 320 × 229 | [PNG](https://flagcdn.com/w320/xk.png) |
