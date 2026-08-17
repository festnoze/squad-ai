# VELOCITRON

Course anti-gravite dans le navigateur, inspiree de Wipeout. Trois circuits,
trois environnements complets, un appareil, trois rivaux et trois tours.

Three.js r169 vendorise, **zero build et zero dependance**. Les textures de
surface sont peintes dans un canvas 2D, les panoramas sont des assets locaux,
les sons sont synthetises en Web Audio et la geometrie est generee en code.

Les environnements partagent un controleur unique (panorama, parallax, vent,
brouillard, reponse a la vitesse et materiel de piste), puis ajoutent leur
logique propre : megapole nocturne, littoral marin ou faille psychedelique.

![Circuit Akari](docs/screenshot.jpeg)

## Lancer

```bash
cd Brainstorming/games/wipeout
python serve.py            # port 8093
```

Puis ouvrir http://localhost:8093/index.html

`serve.py` envoie `Cache-Control: no-store` : sans ca Chrome garde les modules
ES en cache et on rejoue l'ancien build apres une modification.

`python -m http.server 8093` marche aussi, au prix du cache.

## Commandes (AZERTY)

| Touche | Action |
|---|---|
| `Z` | Accelerer |
| `S` | Freiner / reculer |
| `Q` `D` | Diriger |
| `A` `E` | Aerofreins (virages serres, derapage controle) |
| `ESPACE` | Turbo (consomme de l'energie, se recharge) |
| `R` | Se remettre sur la piste |
| `C` | Camera poursuite / cockpit |
| `M` | Couper le son |
| `ECHAP` | Pause |

Les fleches et `ZQSD` cohabitent, `Shift` gauche/droite double les aerofreins.

## Piloter

Le pilotage n'est pas celui d'une voiture : l'appareil glisse. Un virage
pousse vers l'exterieur proportionnellement au **carre** de la vitesse, et la
direction seule ne suffit pas a le tenir a pleine vitesse : il faut lever le
pied avant l'entree, puis ouvrir a l'aerofrein interieur (`A` a gauche, `E` a
droite) pour pivoter plus vite que le gouvernail ne le permet.

Le devers annule une partie de cette charge : le grand 180 releve a 45 degres
passe beaucoup plus vite que le double apex a plat de la section technique, qui
est le point le plus lent du tour.

Frotter un mur coute du bouclier et beaucoup de vitesse. A zero bouclier
l'appareil explose et repart sur la piste ; `R` remet en piste manuellement mais
ne rend que 35 % de bouclier et se recharge en 3 secondes.

Les chevrons oranges au sol sont des plaques de turbo, elles sont gratuites.
Le turbo `ESPACE` consomme un tiers de la reserve, qui se recharge seule.

Ordre de grandeur : l'IA tourne en 24 s au tour, la pointe est a 524 km/h
(705 km/h sous turbo).

## Le fantome

Votre meilleur tour est enregistre, garde s'il bat le record, et **conserve
entre deux sessions** (`localStorage`). Il rejoue ensuite en appareil
translucide que vous pouvez suivre, avec l'ecart en temps reel affiche au HUD
(`FANTOME -0.42` = vous avez 0,42 s d'avance sur votre record).

Un tour n'est retenu que s'il est valide : une remise en piste (`R`) ou une
destruction l'invalide. Le record est affiche sur le menu et s'efface avec
`EFFACER LE RECORD`.

L'enregistrement est fait **en espace piste** (`s, x, h, yaw, roll, pitch`
toutes les 40 ms), donc environ 25 Ko par tour et un rejeu qui reste valable
meme si le decor change.

## Architecture

| Fichier | Role |
|---|---|
| `src/config.js` | Toutes les constantes de reglage et la palette |
| `src/textures.js` | Generation procedurale de toutes les textures |
| `src/track.js` | Spline du circuit, frames, geometrie de piste |
| `src/ship.js` | Maillage de l'appareil et physique anti-gravite |
| `src/ai.js` | Pilotes rivaux (ligne de course + profil de vitesse) |
| `src/race.js` | Grille, decompte, tours, checkpoints, classement |
| `src/world.js` | Ciel, ville, lumieres, trafic, decor |
| `src/environment.js` | Panoramas, logique environnementale partagee, detail de piste |
| `src/themed-world.js` | Ocean, falaises, architecture cotiere, cristaux et faille |
| `src/levels.js` | Identite, spline et profil materiau des trois circuits |
| `src/fx.js` | Particules, reacteurs, trainees, explosions |
| `src/post.js` | Bloom, flou radial, aberration, grain, tonemapping ACES |
| `src/ghost.js` | Enregistrement, persistance et rejeu du meilleur tour |
| `src/audio.js` | Moteur, musique et effets, tout synthetise en Web Audio |
| `src/hud.js` | Interface de course (jauge, minimap, classement) |
| `src/input.js` | Clavier |
| `src/main.js` | Assemblage, machine a etats, camera, boucle |
| `docs/CONTRACTS.md` | Contrats de modules (source de verite) |

Le detail des conventions (espace piste `(s, x, h, yaw)`, orientation du
maillage nez vers `-Z`, rendu HDR lineaire puis tonemapping manuel) est dans
`docs/CONTRACTS.md`.

## Debug

`window.game` expose `{ track, ships, race, post, world, audio, hud, renderer, scene, camera }`.
`?debug` dans l'URL fait exactement deux choses : le nombre d'images par seconde
est ecrit dans le titre de l'onglet, et les deux avertissements console du
fantome (indisponible / desactive) cessent d'etre silencieux. Il n'y a pas
d'affichage de mise au point a l'ecran.
