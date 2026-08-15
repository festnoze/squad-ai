// A01 - terrain spherique a LOD : un quadtree par face de cube-sphere.
//
// Tout vit en ESPACE LOCAL PLANETE (origine = centre de la planete, +Y = axe
// des poles). Ce module ne connait ni viewOrigin ni la position absolue de la
// planete : c'est world/planet.js qui place `object3D`.
//
// Regles de non-regression visuelle :
//  - un noeud parent ne masque ses propres meshes que quand ses 4 enfants ont
//    un mesh pret (donc jamais de trou),
//  - hysteresis sur le merge pour eviter le clignotement,
//  - au plus MAX_IN_FLIGHT requetes de patch simultanees, les plus proches de
//    la camera d'abord.

import * as THREE from 'three';
import { CUBE_FACES, clamp, faceUVToUnit } from '../core/math.js';
import { Emitter } from '../core/events.js';

const MAX_IN_FLIGHT = 4;
// Nombre maximal de subdivisions / fusions par appel a update().
const MAX_STRUCT_OPS = 24;
const MERGE_HYSTERESIS = 1.25;
const MAX_FAILURES = 3;
// Niveau minimal toujours subdivise : sans lui, une planete vue de l'orbite
// n'aurait que 6 patches (un par face de cube) et sa silhouette serait
// nettement facettee. 6 * 4^2 = 96 patches, c'est bon marche.
const MIN_LEVEL = 2;

// Vecteurs temporaires : aucune allocation par frame.
const _dir = new THREE.Vector3();
const _origin = new THREE.Vector3();

let nodeSerial = 0;

export class QuadtreeTerrain {
  constructor({ spec, heightField, pool, material, quality } = {}) {
    this.spec = spec;
    this.heightField = heightField || null;
    this.pool = pool || null;
    this.material = material || null;
    const q = quality || {};
    this.maxDepth = Math.max(0, q.maxLodDepth != null ? q.maxLodDepth : 8);
    this.patchRes = Math.max(5, q.patchRes != null ? q.patchRes : 33);
    this.splitFactor = q.splitFactor != null ? q.splitFactor : 2.6;
    this.minLevel = Math.min(MIN_LEVEL, this.maxDepth);

    this.object3D = new THREE.Group();
    this.object3D.name = `terrain:${spec ? spec.id : 'unknown'}`;

    this._emitter = new Emitter();
    this._cam = new THREE.Vector3();
    this._camLen = 0;
    this._queue = [];
    this._inflight = new Map();
    this._budget = 0;
    this._nodeCount = 0;
    this._meshCount = 0;
    this._deepest = 0;
    this._disposed = false;

    // Rayon conservateur pour le test d'horizon : le point le plus bas
    // possible de la surface (minElevation est negatif).
    const radius = spec ? spec.radius : 1000;
    const minElev = spec && spec.minElevation ? spec.minElevation : 0;
    this._radius = radius;
    this._horizonR = Math.max(1, radius + minElev);

    // Une geante gazeuse n'a pas de sol : pas de quadtree du tout.
    this.roots = [];
    if (spec && !spec.isGas) {
      for (let f = 0; f < CUBE_FACES.length; f++) {
        this.roots.push(this._makeNode(f, -1, -1, 2, 0, 0, 0));
      }
    }
  }

  // -------------------------------------------------------------------------
  // Construction de noeuds
  // -------------------------------------------------------------------------

  _makeNode(faceId, u0, v0, size, level, i, j) {
    const centerDir = faceUVToUnit(faceId, u0 + size * 0.5, v0 + size * 0.5, new THREE.Vector3());
    centerDir.normalize();
    const elev = this.heightField ? this.heightField.elevationUnit(centerDir) : 0;
    const centerLen = this._radius + elev;
    const center = centerDir.clone().multiplyScalar(centerLen);
    // Rayon englobant genereux : un patch de cote `size` couvre au plus
    // size * radius d'arc, on prend 0.9 pour rester dans l'esprit du contrat.
    const boundRadius = Math.max(1, size * this._radius * 0.9);

    this._nodeCount++;
    nodeSerial++;
    return {
      key: `f${faceId}-${level}-${i}-${j}`,
      serial: nodeSerial,
      faceId,
      u0,
      v0,
      size,
      level,
      i,
      j,
      centerDir,
      center,
      centerLen,
      boundRadius,
      children: null,
      mesh: null,
      requested: false,
      failures: 0,
      failed: false,
      destroyed: false,
      dist: Infinity,
      info: null,
    };
  }

  _split(node) {
    const h = node.size * 0.5;
    const l = node.level + 1;
    const i2 = node.i * 2;
    const j2 = node.j * 2;
    node.children = [
      this._makeNode(node.faceId, node.u0, node.v0, h, l, i2, j2),
      this._makeNode(node.faceId, node.u0 + h, node.v0, h, l, i2 + 1, j2),
      this._makeNode(node.faceId, node.u0, node.v0 + h, h, l, i2, j2 + 1),
      this._makeNode(node.faceId, node.u0 + h, node.v0 + h, h, l, i2 + 1, j2 + 1),
    ];
  }

  _merge(node) {
    if (!node.children) return;
    for (let k = 0; k < 4; k++) this._destroySubtree(node.children[k]);
    node.children = null;
  }

  _destroySubtree(node) {
    if (node.children) {
      for (let k = 0; k < 4; k++) this._destroySubtree(node.children[k]);
      node.children = null;
    }
    node.destroyed = true;
    this._nodeCount--;
    this._cancel(node);
    this._dropMesh(node);
  }

  _cancel(node) {
    const entry = this._inflight.get(node.key);
    if (!entry) return;
    this._inflight.delete(node.key);
    node.requested = false;
    if (this.pool && typeof this.pool.cancel === 'function' && entry.reqId !== undefined) {
      try {
        this.pool.cancel(entry.reqId);
      } catch (err) {
        // Une annulation trop tardive n'est pas une erreur fatale.
      }
    }
  }

  _dropMesh(node) {
    const mesh = node.mesh;
    if (!mesh) return;
    node.mesh = null;
    node.info = null;
    this._meshCount--;
    this.object3D.remove(mesh);
    if (mesh.geometry) mesh.geometry.dispose();
    mesh.userData.patchCenter = null;
    this._emitter.emit('patchRemoved', node.key);
  }

  // -------------------------------------------------------------------------
  // Requetes de patch
  // -------------------------------------------------------------------------

  _dispatch() {
    if (!this.pool || this._disposed) return;
    let slots = MAX_IN_FLIGHT - this._inflight.size;
    if (slots <= 0 || this._queue.length === 0) return;
    // Les patches les plus proches de la camera d'abord.
    if (this._queue.length > 1) this._queue.sort(byDistance);
    for (let n = 0; n < this._queue.length && slots > 0; n++) {
      const node = this._queue[n];
      if (node.destroyed || node.mesh || node.requested || node.failed) continue;
      this._request(node);
      slots--;
    }
  }

  _request(node) {
    const msg = {
      type: 'patch',
      faceId: node.faceId,
      u0: node.u0,
      v0: node.v0,
      size: node.size,
      res: this.patchRes,
    };
    node.requested = true;
    let promise;
    try {
      promise = this.pool.request(msg);
    } catch (err) {
      node.requested = false;
      node.failures++;
      if (node.failures >= MAX_FAILURES) node.failed = true;
      return;
    }
    this._inflight.set(node.key, { node, reqId: msg.id });
    promise.then(
      (patch) => this._onPatch(node, patch),
      (err) => this._onPatchError(node, err),
    );
  }

  _onPatchError(node, err) {
    this._inflight.delete(node.key);
    node.requested = false;
    node.failures++;
    if (node.failures >= MAX_FAILURES) {
      node.failed = true;
      console.warn(`[quadtreeTerrain] patch ${node.key} abandonne`, err);
    }
  }

  _onPatch(node, patch) {
    this._inflight.delete(node.key);
    node.requested = false;
    if (this._disposed || node.destroyed || !patch || node.mesh) return;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(patch.position, 3));
    if (patch.normal) geometry.setAttribute('normal', new THREE.BufferAttribute(patch.normal, 3));
    if (patch.color) geometry.setAttribute('color', new THREE.BufferAttribute(patch.color, 3));
    if (patch.uv) geometry.setAttribute('uv', new THREE.BufferAttribute(patch.uv, 2));
    if (patch.index) geometry.setIndex(new THREE.BufferAttribute(patch.index, 1));

    const boundRadius = patch.boundRadius > 0 ? patch.boundRadius : node.boundRadius;
    // Positions relatives au centre du patch : la sphere englobante est
    // centree sur l'origine de la geometrie. On la pose a la main pour eviter
    // un computeBoundingSphere inutile.
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), boundRadius);

    const mesh = new THREE.Mesh(geometry, this.material);
    mesh.name = node.key;
    if (patch.center) {
      mesh.position.set(patch.center[0], patch.center[1], patch.center[2]);
      // Le centre renvoye par le worker est la reference : on aligne le noeud.
      node.center.copy(mesh.position);
      node.centerLen = node.center.length();
    } else {
      mesh.position.copy(node.center);
    }
    node.boundRadius = boundRadius;
    mesh.frustumCulled = true;
    mesh.visible = false;
    mesh.matrixAutoUpdate = false;
    mesh.updateMatrix();
    // Lu par terrainMaterial.onBeforeRender (materiau partage entre patches).
    mesh.userData.patchCenter = mesh.position;
    mesh.userData.patchKey = node.key;

    node.mesh = mesh;
    this._meshCount++;
    this.object3D.add(mesh);

    node.info = {
      key: node.key,
      faceId: node.faceId,
      u0: node.u0,
      v0: node.v0,
      size: node.size,
      level: node.level,
      center: node.center.clone(),
      boundRadius,
      mesh,
      biomeHistogram: patch.biomeHistogram || null,
      waterFraction: typeof patch.waterFraction === 'number' ? patch.waterFraction : 0,
      minElev: typeof patch.minElev === 'number' ? patch.minElev : 0,
      maxElev: typeof patch.maxElev === 'number' ? patch.maxElev : 0,
    };
    this._emitter.emit('patchReady', node.info);
  }

  // -------------------------------------------------------------------------
  // Boucle
  // -------------------------------------------------------------------------

  /**
   * @param {THREE.Vector3} cameraLocal position de la camera en espace local planete
   * @param {number} dt secondes
   */
  update(cameraLocal, dt) {
    if (this._disposed || this.roots.length === 0) return;
    if (cameraLocal) this._cam.copy(cameraLocal);
    this._camLen = this._cam.length();
    this._budget = MAX_STRUCT_OPS;
    this._queue.length = 0;
    this._deepest = 0;

    for (let r = 0; r < this.roots.length; r++) this._evaluate(this.roots[r]);
    this._dispatch();
    for (let r = 0; r < this.roots.length; r++) this._display(this.roots[r]);
  }

  _evaluate(node) {
    const dist = node.center.distanceTo(this._cam);
    node.dist = dist;
    if (node.level > this._deepest) this._deepest = node.level;
    if (!node.mesh && !node.requested && !node.failed) this._queue.push(node);

    const splitDist = node.boundRadius * this.splitFactor;
    const forced = node.level < this.minLevel;

    if (node.children) {
      if (!forced && dist > splitDist * MERGE_HYSTERESIS && this._budget > 0) {
        this._budget--;
        this._merge(node);
        return;
      }
      for (let k = 0; k < 4; k++) this._evaluate(node.children[k]);
      return;
    }

    if (node.level < this.maxDepth && (forced || dist < splitDist) && this._budget > 0) {
      this._budget--;
      this._split(node);
      for (let k = 0; k < 4; k++) this._evaluate(node.children[k]);
    }
  }

  /** @returns {boolean} true si la zone du noeud est entierement couverte. */
  _display(node) {
    if (node.children) {
      let all = true;
      for (let k = 0; k < 4; k++) {
        if (!this._display(node.children[k])) all = false;
      }
      if (all) {
        if (node.mesh) node.mesh.visible = false;
        return true;
      }
      // Subdivision incomplete : on remonte au parent plutot que de laisser
      // un trou. Les enfants deja prets sont masques (pas de superposition).
      for (let k = 0; k < 4; k++) this._hideSubtree(node.children[k]);
      return this._show(node);
    }
    return this._show(node);
  }

  _show(node) {
    if (!node.mesh) return false;
    node.mesh.visible = !this._beyondHorizon(node);
    // Le noeud couvre sa zone meme s'il est masque par l'horizon : rien de
    // visible ne peut se trouver derriere.
    return true;
  }

  _hideSubtree(node) {
    if (node.mesh) node.mesh.visible = false;
    if (node.children) {
      for (let k = 0; k < 4; k++) this._hideSubtree(node.children[k]);
    }
  }

  /**
   * Culling d'horizon volontairement conservateur : on additionne l'angle
   * d'horizon vu de la camera, celui vu du patch et l'extension angulaire du
   * patch, plus une marge. Un patch encore visible ne disparait jamais.
   */
  _beyondHorizon(node) {
    const camLen = this._camLen;
    const R = this._horizonR;
    // Camera au sol ou sous la surface : on ne coupe rien.
    if (camLen <= R * 1.001) return false;
    // Patch proche : jamais coupe.
    if (node.dist < node.boundRadius * 2) return false;

    const rNode = node.centerLen + node.boundRadius;
    const a1 = Math.acos(clamp(R / camLen, -1, 1));
    const a2 = Math.acos(clamp(R / Math.max(rNode, R), -1, 1));
    const a3 = Math.asin(clamp(node.boundRadius / Math.max(rNode, 1e-3), -1, 1));
    const limit = a1 + a2 + a3 + 0.06;
    if (limit >= Math.PI) return false;

    _dir.copy(node.center).divideScalar(Math.max(node.centerLen, 1e-6));
    _origin.copy(this._cam).divideScalar(Math.max(camLen, 1e-6));
    return _dir.dot(_origin) < Math.cos(limit);
  }

  // -------------------------------------------------------------------------
  // API publique
  // -------------------------------------------------------------------------

  get stats() {
    return {
      nodes: this._nodeCount,
      meshes: this._meshCount,
      pending: this._inflight.size,
      depth: this._deepest,
    };
  }

  /** @param {(p: object) => void} cb @returns {() => void} desabonnement */
  onPatchReady(cb) {
    return this._emitter.on('patchReady', cb);
  }

  /** @param {(key: string) => void} cb @returns {() => void} desabonnement */
  onPatchRemoved(cb) {
    return this._emitter.on('patchRemoved', cb);
  }

  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    for (let r = 0; r < this.roots.length; r++) this._destroySubtree(this.roots[r]);
    this.roots.length = 0;
    this._inflight.clear();
    this._queue.length = 0;
    this.object3D.clear();
    this._emitter.clear();
    // Le materiau et les textures appartiennent a l'appelant (partages).
    this.material = null;
    this.pool = null;
  }
}

function byDistance(a, b) {
  return a.dist - b.dist;
}
