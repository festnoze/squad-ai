# 🛰️ Orbiter

Visualisation et navigation 3D d'un **système solaire réduit** — Soleil, Terre,
Lune, Mars — avec une vraie **mécanique orbitale** (calcul des trajectoires),
l'ajout de **satellites artificiels**, et les **points remarquables** : orbite
géostationnaire (et sélénostationnaire), points de **Lagrange** (L1–L5), **L2**,
et une **NRHO** type Gateway autour de la Lune.

Stack : **Vite + TypeScript + Three.js**. La couche physique est pure (sans
dépendance au rendu) et **testée** (Vitest).

## Démarrer

```bash
npm install
npm run dev      # http://localhost:5173
npm test         # tests de la mécanique orbitale
npm run build    # tsc + bundle de production
```

## Navigation

- **Repères** : Système solaire (héliocentrique), Terre–Lune, Lune, Mars — chacun
  avec sa propre échelle (les distances réelles sont gérées par repère).
- **Souris** : orbite / zoom / pan (OrbitControls). Clique un corps, un satellite
  ou un point de Lagrange pour l'inspecter.
- **Temps** : lecture/pause, « aujourd'hui », vitesse de −10⁷ à +10⁷ s/s.
- **Satellites** : choisis une présélection (orbite calculée par les formules) →
  *Ajouter*. GEO, ISS/LEO, sélénostationnaire, NRHO, aréostationnaire, transfert
  de Hohmann Terre→Mars.

## Les formules (couche `src/physics`)

| Sujet | Formule | Fichier |
| --- | --- | --- |
| Mouvement moyen | n = √(μ/a³) | `orbit.ts` |
| Équation de Kepler | M = E − e·sin E (Newton) | `orbit.ts` |
| Anomalie vraie | ν = 2·atan2(√(1+e)·sin(E/2), √(1−e)·cos(E/2)) | `orbit.ts` |
| Élements → état | rotation périfocale → inertiel par (Ω, i, ω) | `orbit.ts` |
| État → éléments | vecteur excentricité, moment cinétique, nœud | `orbit.ts` |
| Éphémérides | éléments Keplériens J2000 + dérivées séculaires (JPL) ; Lune en éléments moyens géocentriques | `bodies.ts` |
| Orbite stationnaire | r = (μ / ω²)^⅓, ω = 2π/T_sidéral | `points.ts` |
| Lagrange L1–L3 | racine du quintique colinéaire (Newton) | `points.ts` |
| Lagrange L4/L5 | triangle équilatéral exact (±60°) | `points.ts` |
| Sphère de Hill | r_H ≈ a·(m₂/3m₁)^⅓ | `points.ts` |
| NRHO | **approximation** : ellipse képlérienne quasi-polaire à forte excentricité, apolune côté L2 | `points.ts` |

### Valeurs de référence calculées

- **GEO** : r = (μ⊕/ω⊕²)^⅓ ≈ **42 164 km** (ω⊕ = 2π/jour sidéral).
- **Sélénostationnaire** : ≈ **88 000 km** — au-delà de la **sphère de Hill** de la
  Lune (~58 000 km), donc **théorique / instable** (affichée pour la formule).
- **Lagrange Terre–Lune** : μ = m_Lune/(m_Terre+m_Lune) ≈ 0,0121 ; L1/L2 à ±~61 500 km
  de la Lune.
- **Lagrange Soleil–Terre** : L2 (≈ 1,5 M km, anti-Soleil) — l'orbite de JWST.

## Précision & limites (assumées)

- Les **tailles des corps sont exagérées** pour la lisibilité (sinon invisibles à
  l'échelle des distances) ; les **positions/orbites** sont à l'échelle dans chaque
  repère.
- Éphémérides à **précision moyenne** (fraction de degré) — pour la navigation et
  la pédagogie, pas pour de la navigation opérationnelle.
- La **NRHO** et les points de Lagrange sont affichés dans le **plan orbital
  instantané** Terre–Lune ; une NRHO rigoureuse exige une correction différentielle
  dans le problème circulaire restreint à 3 corps (CR3BP), hors périmètre ici.

## Architecture

```
src/
  physics/   constantes, vecteurs, Kepler/éléments, éphémérides, points remarquables (+ tests)
  sim/       horloge de simulation, monde (corps + satellites, présélections)
  render/    scène Three.js, repères multi-échelle, orbites, marqueurs, picking, labels
  main.ts    câblage UI (navigation, temps, points, satellites, sélection)
```
