/**
 * Material library. Wraps the procedural texture sets in MeshStandardMaterial /
 * MeshPhysicalMaterial instances with sensible PBR parameters, and memoises them so the
 * whole city shares a handful of GPU pipelines.
 *
 * The ORM packing convention from TextureFactory (AO=R, roughness=G, metalness=B) means
 * one texture fetch feeds three inputs.
 */

import {
  MeshStandardMaterial, MeshPhysicalMaterial, Color, Vector2, DoubleSide, FrontSide,
} from 'three/webgpu';
import { getPBR } from './TextureFactory.js';

const materials = new Map();

/**
 * @param {object} opts
 * @param {string} opts.texture generator name from TextureFactory
 * @param {number} [opts.size] texture resolution
 * @param {number} [opts.repeat] UV repeat (world-space tiling is applied per-geometry)
 * @param {number} [opts.normalScale]
 * @param {boolean} [opts.physical] use MeshPhysicalMaterial (clearcoat / transmission)
 */
function build({
  texture, size = 512, repeat = 1, normalScale = 1, color = 0xffffff,
  physical = false, roughness = 1, metalness = 1, envMapIntensity = 1,
  clearcoat = 0, clearcoatRoughness = 0.1, side = FrontSide,
  emissiveFromAlbedo = false, emissive = 0xffc98a, ...rest
}) {
  const set = getPBR(texture, size);
  // Cloning lets each material own its repeat without duplicating pixel data.
  const map = set.map.clone();
  const normalMap = set.normalMap.clone();
  const orm = set.roughnessMap.clone();
  for (const t of [map, normalMap, orm]) {
    t.repeat.set(repeat, repeat);
    t.needsUpdate = true;
  }

  const Ctor = physical ? MeshPhysicalMaterial : MeshStandardMaterial;
  const mat = new Ctor({
    color: new Color(color),
    // Vertex colours let one shared material paint thousands of individually tinted
    // surfaces (see GeometryBuilder.setColor) without extra draw calls.
    vertexColors: true,
    map,
    normalMap,
    normalScale: new Vector2(normalScale, normalScale),
    roughnessMap: orm,
    metalnessMap: orm,
    aoMap: orm,
    aoMapIntensity: 0.85,
    roughness,
    metalness,
    envMapIntensity,
    side,
    ...rest,
  });

  if (emissiveFromAlbedo) {
    // Reuse the albedo as an emissive mask. The curtain-wall generator already varies
    // brightness pane by pane, so driving emissiveIntensity with the time of day lights
    // a plausible scatter of windows across every tower for the cost of one texture
    // slot - no per-window geometry, no extra draw calls.
    mat.emissiveMap = map;
    mat.emissive = new Color(emissive);
    mat.emissiveIntensity = 0;
  }
  if (physical) {
    mat.clearcoat = clearcoat;
    mat.clearcoatRoughness = clearcoatRoughness;
  }
  return mat;
}

const RECIPES = {
  road: () => build({ texture: 'asphalt', size: 1024, repeat: 1, normalScale: 1.1, metalness: 0.0, envMapIntensity: 0.5 }),
  sidewalk: () => build({ texture: 'sidewalk', size: 512, normalScale: 0.9, metalness: 0.0, envMapIntensity: 0.6 }),
  concrete: () => build({ texture: 'concrete', size: 512, normalScale: 0.8, metalness: 0.0, envMapIntensity: 0.7 }),
  brick: () => build({ texture: 'brick', size: 512, normalScale: 1.0, metalness: 0.0, envMapIntensity: 0.6 }),
  glassTower: () => build({
    texture: 'curtainWall', size: 512, normalScale: 0.7,
    metalness: 1.0, roughness: 1.0, envMapIntensity: 1.6,
    physical: true, clearcoat: 0.6, clearcoatRoughness: 0.05,
    emissiveFromAlbedo: true, emissive: 0xffcf8f,
  }),
  roof: () => build({ texture: 'roof', size: 512, normalScale: 1.1, metalness: 0.0, envMapIntensity: 0.4 }),
  sand: () => build({ texture: 'sand', size: 512, normalScale: 1.0, metalness: 0.0, envMapIntensity: 0.8 }),
  grass: () => build({ texture: 'grass', size: 512, normalScale: 1.0, metalness: 0.0, envMapIntensity: 0.6 }),
  metal: () => build({ texture: 'metalPanel', size: 512, normalScale: 0.7, envMapIntensity: 1.3 }),
  corrugated: () => build({ texture: 'corrugated', size: 512, normalScale: 1.2, envMapIntensity: 1.0 }),
  wood: () => build({ texture: 'wood', size: 512, normalScale: 1.0, metalness: 0.0, envMapIntensity: 0.5 }),
};

/** Fetch a shared material by recipe name. */
export function getMaterial(name) {
  if (!materials.has(name)) {
    const recipe = RECIPES[name];
    if (!recipe) throw new Error(`Unknown material recipe: ${name}`);
    materials.set(name, recipe());
  }
  return materials.get(name);
}

/**
 * Variant of a recipe with a different UV repeat - needed because a 4 m sidewalk slab and
 * a 200 m road want the same pixels at very different densities.
 */
export function getTiledMaterial(name, repeat) {
  const key = `${name}@${repeat}`;
  if (!materials.has(key)) {
    const base = getMaterial(name);
    const m = base.clone();
    for (const slot of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap']) {
      if (m[slot]) {
        m[slot] = m[slot].clone();
        m[slot].repeat.set(repeat, repeat);
        m[slot].needsUpdate = true;
      }
    }
    materials.set(key, m);
  }
  return materials.get(key);
}

/** Flat coloured material for gizmos, lights, decals, foliage. */
export function getFlat(color, opts = {}) {
  const key = `flat:${color}:${JSON.stringify(opts)}`;
  if (!materials.has(key)) {
    materials.set(key, new MeshStandardMaterial({
      color: new Color(color), roughness: 0.6, metalness: 0.1, vertexColors: true, ...opts,
    }));
  }
  return materials.get(key);
}

/**
 * Car paint: a dielectric base coat under a clearcoat lacquer.
 *
 * Metalness stays low deliberately. Real metallic paint is a dielectric binder with
 * suspended flake, not a metal surface - pushing `metalness` up kills the diffuse term
 * and every car turns into a black mirror that only shows the sky.
 */
export function makeCarPaint(color) {
  const key = `paint:${color}`;
  if (!materials.has(key)) {
    const m = new MeshPhysicalMaterial({
      color: new Color(color),
      metalness: 0.15,
      roughness: 0.42,
      clearcoat: 0.55,
      clearcoatRoughness: 0.12,
      // Keep sky reflections from washing the paint colour out at grazing angles.
      envMapIntensity: 0.7,
    });
    materials.set(key, m);
  }
  return materials.get(key);
}

/**
 * Tinted automotive glass. Reflective rather than transmissive: real transmission needs
 * a backdrop render, is expensive per car, and at this tint reads no differently from a
 * dark reflective surface.
 */
export function getCarGlass() {
  if (!materials.has('carGlass')) {
    materials.set('carGlass', new MeshPhysicalMaterial({
      color: 0x10161d,
      metalness: 0.0,
      roughness: 0.08,
      reflectivity: 0.9,
      clearcoat: 1.0,
      clearcoatRoughness: 0.04,
      envMapIntensity: 1.4,
      side: DoubleSide,
    }));
  }
  return materials.get('carGlass');
}

export function disposeMaterials() {
  for (const m of materials.values()) m.dispose?.();
  materials.clear();
}
