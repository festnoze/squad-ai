// Le systeme solaire : detient les 12 planetes, decide laquelle est "active"
// (terrain LOD monte) et les place en espace vue a chaque frame.

import * as THREE from 'three';
import { SCALE, getQuality } from '../core/settings.js';
import { Planet } from './planet.js';

const _v1 = new THREE.Vector3();
const _near = { planet: null, distance: Infinity, altitude: Infinity };

export class SolarSystem {
  constructor({ scene, system, quality = getQuality() }) {
    this.scene = scene;
    this.system = system;
    this.star = system.star;
    this.quality = quality;

    this.planets = system.planets.map((spec) => new Planet({ spec, quality }));
    this.root = new THREE.Group();
    this.root.name = 'solar-system';
    for (const p of this.planets) this.root.add(p.object3D);

    this.orbitLines = this._buildOrbitLines();
    this.root.add(this.orbitLines);
    scene.add(this.root);

    this.activePlanet = null;
    this._activationLock = false;
  }

  _buildOrbitLines() {
    const group = new THREE.Group();
    group.name = 'orbits';
    const material = new THREE.LineBasicMaterial({
      color: 0x2f5f78,
      transparent: true,
      opacity: 0.1,
      depthWrite: false,
    });
    const SEG = 256;
    for (const p of this.planets) {
      const pts = new Float32Array(SEG * 3);
      for (let i = 0; i < SEG; i++) {
        const a = (i / SEG) * Math.PI * 2;
        pts[i * 3] = Math.cos(a) * p.spec.orbitRadius;
        pts[i * 3 + 1] = 0;
        pts[i * 3 + 2] = Math.sin(a) * p.spec.orbitRadius;
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pts, 3));
      const loop = new THREE.LineLoop(geo, material);
      loop.frustumCulled = false;
      group.add(loop);
    }
    group.visible = true;
    return group;
  }

  planetById(id) {
    return this.planets.find((p) => p.spec.id === id) || null;
  }

  /** Planete la plus proche en distance de surface. */
  nearestPlanet(absPos) {
    let best = null;
    let bestScore = Infinity;
    for (const p of this.planets) {
      const d = p.distanceTo(absPos) - p.spec.radius;
      if (d < bestScore) {
        bestScore = d;
        best = p;
      }
    }
    _near.planet = best;
    _near.distance = best ? best.distanceTo(absPos) : Infinity;
    _near.altitude = best ? best.altitudeOf(absPos) : Infinity;
    return _near;
  }

  /** Planete dans la sphere d'influence, ou null si on est dans le vide. */
  currentPlanet(absPos) {
    for (const p of this.planets) {
      if (p.distanceTo(absPos) < p.spec.radius * SCALE.DEACTIVATE_RADII) return p;
    }
    return null;
  }

  update(dt, ctx) {
    // ctx = { viewOrigin, cameraAbsPos, elapsed }
    this._manageActivation(ctx.cameraAbsPos);
    for (const p of this.planets) p.update(dt, ctx);
    // Les orbites sont centrees sur le soleil, donc a l'origine absolue.
    this.orbitLines.position.set(-ctx.viewOrigin.x, -ctx.viewOrigin.y, -ctx.viewOrigin.z);
  }

  _manageActivation(absPos) {
    // Une seule activation a la fois : monter un terrain cree des workers et
    // beaucoup de geometrie, on evite les tempetes.
    for (const p of this.planets) {
      const d = p.distanceTo(absPos);
      const wantActive = d < p.spec.radius * SCALE.ACTIVATE_RADII;
      const mustDrop = d > p.spec.radius * SCALE.DEACTIVATE_RADII;

      if (wantActive && !p.isActive && !p.isBusy && !this._activationLock) {
        this._activationLock = true;
        p.activate().finally(() => {
          this._activationLock = false;
          if (p.isActive) this.activePlanet = p;
        });
      } else if (mustDrop && p.isActive) {
        p.deactivate();
        if (this.activePlanet === p) this.activePlanet = null;
      }
    }
    if (this.activePlanet && !this.activePlanet.isActive) this.activePlanet = null;
    if (!this.activePlanet) {
      const found = this.planets.find((p) => p.isActive);
      if (found) this.activePlanet = found;
    }
  }

  setOrbitLinesVisible(v) {
    this.orbitLines.visible = v;
  }

  dispose() {
    for (const p of this.planets) p.dispose();
    this.scene.remove(this.root);
    this.orbitLines.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
  }
}
