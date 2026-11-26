# DOORFADE - door frames go with their wall (2026-11-24)

## Demande

Une fois une porte passee, son encadrement (montants + linteau, et le battant) doit disparaitre quand il est au premier
plan entre la camera et le joueur, exactement comme le mur auquel il appartient (capture 14.png, level8 : la chaise rouge
vient d'entrer dans la cuisine, le mur s'est efface mais le grand cadre bois reste devant).

## Cause

Les encadrements etaient deja enregistres dans le WallFader avec le plan et la regle de leur mur (LevelBuilder.DoorDecor :
meme fader, meme point, meme normale, meme regle outer/shared). Mais `RegisterWallLooks` les marquait ensuite
`KeepDoor` (regle M9 "doors never move" du 2026-11-19), et `WallFader.Step` forcait `hidden &= !e.Door` : un element de
porte ne bougeait dans aucun look, mur proche compris. `KeepDoor` posait aussi `KeepWhenLowered`.

## Correctif

`Assets/Scripts/Runtime/WallFader.cs` uniquement (cote runtime) :
- suppression de `hidden &= !e.Door` (ex `MUTATION:DOORS_STAND`) : un element de porte suit la regle de plan de son mur ;
- `KeepDoor` ne pose plus `KeepWhenLowered` : en look abaisse, le cadre descend avec le mur ;
- le flag `Door` sert encore a une chose : un battant ne suit jamais la regle de la boite (LEAF_FADE), seulement le plan de
  son mur (nouveau marqueur `MUTATION:DOORS_NO_BOX`, mutation.sh mis a jour).

Consequences, toutes par la regle existante (aucune nouvelle regle, aucun reglage) :
- porte interieure : le cadre part quand le plan de son mur separe la camera du joueur, quelle que soit la piece ;
- porte exterieure / d'entree : regle outer (camera dehors), le battant decoratif "DoorLeaf" part avec ; mur proche qui
  s'evanouit (near walls) : ses cadres s'evanouissent aussi ;
- battants reels (DoorLeaf, ouverts ou fermes) : plan du mur, comme le cadre ;
- meme duree (Tuning.WallFadeSeconds), meme materiau fantome, meme bascule ShadowsOnly : collider, ombre, vision, ouie et
  logique de porte inchanges (visuel uniquement) ;
- pas de clignotement propre au cadre : il bascule exactement au meme instant que son mur (meme test de plan, meme
  position cible). Le mur lui-meme n'a pas d'hysteresis sur le plan (seulement sur la couverture des murs proches, que les
  cadres partagent).
- Spectateur et tournee du titre (cible = camera) : les murs partages ne s'effacent jamais (camera et cible du meme cote),
  les murs exterieurs s'effacent camera dehors ; les cadres font pareil, donc pas de cadre flottant dans un mur efface ni
  d'apparition propre au cadre.

Tests mis a jour (non lances, consigne) pour la nouvelle regle : Step36l (renomme `Step36l_LeafMovesOnlyWithItsWall`),
Step70b, Step70f (renomme `Step70f_EachLookMovesTheRightPartsWithTheirDoorFrames`), Step90a.

## Rendu

`Assets/Editor/DoorFadeShots.cs` (`-executeMethod OutOfSight.Editor.DoorFadeShots.Shoot`) : level8, camera orbitale de jeu,
joueur juste apres une porte ; `_before` = cadres/battants redessines opaques (ancienne regle), `_after` = fader seul.
Sortie : `Build/shots/doorfade/`. Resultat (1 run Unity, compile propre) : salon vers cuisine, le cadre opaque du `_before`
devient fantome au niveau du mur dans `_after` (abaisse : il descend avec le mur) ; chambre vers cuisine battant ouvert :
cadre et battant partent (2 elements de porte) ; porte d'entree vue de dehors : plus de cadre flottant, seuls les moignons.

## A VERIFIER

- En jeu (level8, level12) : traverser chaque porte interieure dans les deux sens, le cadre part et revient avec son mur.
- Debout pile dans l'embrasure, en tournant la camera : mur et cadre basculent ensemble, sans clignotement visible.
- Look abaisse : le cadre descend avec le mur (le moignon reste) ; look "aucun" : rien ne bouge.
- Porte d'entree vue de dehors (titre, spectateur) : le cadre ne flotte plus et ne "saute" pas pendant la tournee.
- Lisibilite : une porte fermee dans un mur efface est aussi effacee ; l'icone de porte (marqueur) reste le repere.
- Filtres de tests a lancer : `Step70` (wall fader), `Step36l_ Step36o_`, `Step90` (near walls), `Ceiling_`, `Spectator`, `MenuCam_`.
