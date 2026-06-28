import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  BODIES,
  type BodyId,
  GEO_RADIUS,
  LUNAR_STATIONARY_RADIUS,
  MASS,
  elementsToState,
  heliocentricPosition,
  lagrangePositions,
  sampleOrbit,
  type Vec3,
} from "../physics";
import type { World } from "../sim/world";
import { makeLabel } from "./labels";

export type FrameId = "sun" | "earth" | "moon" | "mars";
export type PointKey = "geo" | "lunastat" | "lagrange-em" | "lagrange-se";

interface FrameDef {
  id: FrameId;
  label: string;
  origin: BodyId;
  metersPerUnit: number;
  bodies: BodyId[];
  minBody: number;
  camDist: number;
  hint: string;
}

export const FRAMES: FrameDef[] = [
  {
    id: "sun", label: "☀ Système solaire", origin: "sun", metersPerUnit: 1e9,
    bodies: ["sun", "earth", "moon", "mars"], minBody: 3, camDist: 520,
    hint: "Héliocentrique. Orbites de la Terre et de Mars (la Lune suit la Terre).",
  },
  {
    id: "earth", label: "🌍 Terre–Lune", origin: "earth", metersPerUnit: 2e6,
    bodies: ["earth", "moon"], minBody: 0.5, camDist: 320,
    hint: "Géocentrique. GEO, orbite lunaire, points de Lagrange Terre–Lune, NRHO.",
  },
  {
    id: "moon", label: "🌙 Lune", origin: "moon", metersPerUnit: 1e6, bodies: ["moon", "earth"],
    minBody: 0.4, camDist: 200,
    hint: "Sélénocentrique. Orbite sélénostationnaire (théorique) et NRHO.",
  },
  {
    id: "mars", label: "🔴 Mars", origin: "mars", metersPerUnit: 1e6, bodies: ["mars"],
    minBody: 0.4, camDist: 60, hint: "Aréocentrique. Orbite aréostationnaire.",
  },
];

export interface Selectable {
  kind: "body" | "satellite" | "point";
  id: string;
  name: string;
  note?: string;
}

export class Viewer {
  readonly scene = new THREE.Scene();
  private readonly renderer: THREE.WebGLRenderer;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly sun = new THREE.DirectionalLight(0xffffff, 1.4);
  private readonly dynamic = new THREE.Group();
  private readonly raycaster = new THREE.Raycaster();

  private frame: FrameDef = FRAMES[0];
  private world: World;
  private pointVisible: Record<PointKey, boolean> = {
    geo: true, lunastat: true, "lagrange-em": true, "lagrange-se": false,
  };

  private bodyMeshes = new Map<BodyId, THREE.Mesh>();
  private bodyOrbits = new Map<BodyId, THREE.Line>();
  private rings: { key: PointKey; center: BodyId; radius: number; line: THREE.Line }[] = [];
  private lagrange: { key: PointKey; pair: [BodyId, BodyId]; markers: Map<string, THREE.Object3D> }[] = [];
  private satMeshes = new Map<string, THREE.Mesh>();
  private satOrbits = new Map<string, THREE.Line>();
  private pickables: THREE.Object3D[] = [];
  private satCount = -1;

  onSelect: (sel: Selectable | null) => void = () => {};

  constructor(canvas: HTMLCanvasElement, world: World) {
    this.world = world;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.scene.background = new THREE.Color(0x05070d);
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.01, 1e6);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;

    this.scene.add(new THREE.AmbientLight(0x404a60, 1.2));
    this.scene.add(this.sun);
    this.scene.add(this.dynamic);
    this.addStarfield();

    canvas.addEventListener("pointerdown", (e) => this.pick(e));
    this.setFrame("sun");
    this.resize();
  }

  resize(): void {
    const c = this.renderer.domElement;
    const w = c.clientWidth || window.innerWidth;
    const h = c.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  setFrame(id: FrameId): void {
    this.frame = FRAMES.find((f) => f.id === id) ?? FRAMES[0];
    this.buildFrame();
    const d = this.frame.camDist;
    this.camera.position.set(d * 0.6, -d, d * 0.6);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  setPointVisible(key: PointKey, on: boolean): void {
    this.pointVisible[key] = on;
  }

  // ----------------------------------------------------------------- building

  private clearGroup(): void {
    this.dynamic.clear();
    this.bodyMeshes.clear();
    this.bodyOrbits.clear();
    this.rings = [];
    this.lagrange = [];
    this.satMeshes.clear();
    this.satOrbits.clear();
  }

  private buildFrame(): void {
    this.clearGroup();
    const f = this.frame;

    for (const id of f.bodies) {
      const body = BODIES[id];
      const r = Math.max(body.radius / f.metersPerUnit, f.minBody);
      const mat = id === "sun"
        ? new THREE.MeshBasicMaterial({ color: body.color })
        : new THREE.MeshStandardMaterial({ color: body.color, roughness: 0.85, metalness: 0.0 });
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 24), mat);
      mesh.userData.sel = { kind: "body", id, name: body.name } satisfies Selectable;
      this.dynamic.add(mesh);
      this.bodyMeshes.set(id, mesh);
      const label = makeLabel(body.name, "#" + body.color.toString(16).padStart(6, "0"));
      label.userData.tag = "label";
      mesh.add(label);
      label.position.set(0, 0, r * 1.6);

      if (body.elementsAt) {
        const line = new THREE.Line(
          new THREE.BufferGeometry(),
          new THREE.LineBasicMaterial({ color: body.color, transparent: true, opacity: 0.5 }),
        );
        this.dynamic.add(line);
        this.bodyOrbits.set(id, line);
      }
    }

    // Rings (stationary orbits).
    if (f.bodies.includes("earth")) this.addRing("geo", "earth", GEO_RADIUS, 0x6cf0c2);
    if (f.bodies.includes("moon"))
      this.addRing("lunastat", "moon", LUNAR_STATIONARY_RADIUS, 0xb08cff);

    // Lagrange marker sets.
    this.addLagrange("lagrange-em", ["earth", "moon"]);
    if (f.id === "sun" || f.id === "earth") this.addLagrange("lagrange-se", ["sun", "earth"]);

    this.satCount = -1; // force satellite rebuild
    this.rebuildSatellites();
    this.refreshPickables();
  }

  private addRing(key: PointKey, center: BodyId, radius: number, color: number): void {
    const line = new THREE.LineLoop(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.8 }),
    );
    this.dynamic.add(line);
    this.rings.push({ key, center, radius, line });
  }

  private addLagrange(key: PointKey, pair: [BodyId, BodyId]): void {
    const color = key === "lagrange-em" ? 0xffd14a : 0xff8c42;
    const markers = new Map<string, THREE.Object3D>();
    for (const name of ["L1", "L2", "L3", "L4", "L5"]) {
      const g = new THREE.Group();
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(this.frame.minBody * 0.5 + 0.3, 12, 10),
        new THREE.MeshBasicMaterial({ color }),
      );
      const tag = `${pair[0]}–${pair[1]} ${name}`;
      dot.userData.sel = { kind: "point", id: `${key}-${name}`, name: tag } satisfies Selectable;
      const label = makeLabel(name, "#" + color.toString(16));
      label.position.set(0, 0, 1.5);
      g.add(dot, label);
      this.dynamic.add(g);
      markers.set(name, g);
    }
    this.lagrange.push({ key, pair, markers });
  }

  private rebuildSatellites(): void {
    if (this.satCount === this.world.satellites.length) return;
    for (const m of this.satMeshes.values()) this.dynamic.remove(m);
    for (const l of this.satOrbits.values()) this.dynamic.remove(l);
    this.satMeshes.clear();
    this.satOrbits.clear();
    for (const sat of this.world.satellites) {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(this.frame.minBody * 0.5 + 0.25, 12, 10),
        new THREE.MeshBasicMaterial({ color: sat.color }),
      );
      mesh.userData.sel = {
        kind: "satellite", id: sat.id, name: sat.name, note: sat.note,
      } satisfies Selectable;
      const label = makeLabel(sat.name, "#" + sat.color.toString(16).padStart(6, "0"));
      label.position.set(0, 0, 1.4);
      mesh.add(label);
      this.dynamic.add(mesh);
      this.satMeshes.set(sat.id, mesh);
      const line = new THREE.Line(
        new THREE.BufferGeometry(),
        new THREE.LineBasicMaterial({ color: sat.color, transparent: true, opacity: 0.7 }),
      );
      this.dynamic.add(line);
      this.satOrbits.set(sat.id, line);
    }
    this.satCount = this.world.satellites.length;
    this.refreshPickables();
  }

  private refreshPickables(): void {
    this.pickables = [
      ...this.bodyMeshes.values(),
      ...this.satMeshes.values(),
      ...this.lagrange.flatMap((s) =>
        [...s.markers.values()].map((g) => (g as THREE.Group).children[0]),
      ),
    ];
  }

  // ------------------------------------------------------------------ update

  private origin(t: number): Vec3 {
    return heliocentricPosition(this.frame.origin, t);
  }

  private toScene(helio: Vec3, o: Vec3): THREE.Vector3 {
    const s = this.frame.metersPerUnit;
    return new THREE.Vector3((helio[0] - o[0]) / s, (helio[1] - o[1]) / s, (helio[2] - o[2]) / s);
  }

  update(t: number): void {
    this.rebuildSatellites();
    const f = this.frame;
    const o = this.origin(t);
    const maxUnits = 6000;

    // Sun light direction (from the Sun toward the frame origin).
    const sunScene = this.toScene([0, 0, 0], o);
    this.sun.position.copy(sunScene.lengthSq() === 0 ? new THREE.Vector3(0, 0, 1) : sunScene);

    for (const id of f.bodies) {
      const body = BODIES[id];
      const mesh = this.bodyMeshes.get(id)!;
      mesh.position.copy(this.toScene(heliocentricPosition(id, t), o));
      const orbit = this.bodyOrbits.get(id);
      if (orbit && body.parent && body.elementsAt) {
        const parentHelio = heliocentricPosition(body.parent, t);
        const pts = sampleOrbit(body.elementsAt(t), 220)
          .map((p) => this.toScene([parentHelio[0] + p[0], parentHelio[1] + p[1], parentHelio[2] + p[2]], o));
        const big = pts.some((p) => p.lengthSq() > maxUnits * maxUnits);
        orbit.visible = !big;
        if (!big) orbit.geometry.setFromPoints(pts);
      }
    }

    // Stationary rings.
    for (const ring of this.rings) {
      const on = this.pointVisible[ring.key] && f.bodies.includes(ring.center);
      ring.line.visible = on;
      if (!on) continue;
      const c = heliocentricPosition(ring.center, t);
      const pts: THREE.Vector3[] = [];
      for (let k = 0; k <= 96; k++) {
        const a = (2 * Math.PI * k) / 96;
        pts.push(this.toScene([c[0] + ring.radius * Math.cos(a), c[1] + ring.radius * Math.sin(a), c[2]], o));
      }
      ring.line.geometry.setFromPoints(pts);
    }

    // Lagrange points.
    for (const set of this.lagrange) {
      const on = this.pointVisible[set.key];
      const [aId, bId] = set.pair;
      const p1 = heliocentricPosition(aId, t);
      const p2 = heliocentricPosition(bId, t);
      const secondary = BODIES[bId];
      const st = secondary.elementsAt
        ? elementsToState(secondary.elementsAt(t), BODIES[aId].mu, t)
        : { r: [0, 0, 0] as Vec3, v: [0, 0, 1] as Vec3 };
      const normal: Vec3 = [
        st.r[1] * st.v[2] - st.r[2] * st.v[1],
        st.r[2] * st.v[0] - st.r[0] * st.v[2],
        st.r[0] * st.v[1] - st.r[1] * st.v[0],
      ];
      const L = lagrangePositions(p1, p2, normal, MASS[aId], MASS[bId]);
      for (const name of ["L1", "L2", "L3", "L4", "L5"] as const) {
        const g = set.markers.get(name)!;
        const pos = this.toScene(L[name], o);
        const visible = on && pos.lengthSq() < maxUnits * maxUnits;
        g.visible = visible;
        if (visible) g.position.copy(pos);
      }
    }

    // Satellites.
    for (const sat of this.world.satellites) {
      const mesh = this.satMeshes.get(sat.id);
      if (mesh) mesh.position.copy(this.toScene(this.world.satellitePosition(sat, t), o));
      const line = this.satOrbits.get(sat.id);
      if (line) {
        const c = heliocentricPosition(sat.central, t);
        const pts = sampleOrbit(sat.elements, 220)
          .map((p) => this.toScene([c[0] + p[0], c[1] + p[1], c[2]], o));
        const big = pts.some((p) => p.lengthSq() > maxUnits * maxUnits);
        line.visible = !big;
        if (!big) line.geometry.setFromPoints(pts);
      }
    }

    // Keep labels readable: scale with distance to camera.
    this.dynamic.traverse((obj) => {
      if (obj instanceof THREE.Sprite) {
        const dist = this.camera.position.distanceTo(obj.getWorldPosition(new THREE.Vector3()));
        const s = (dist * 0.03) * (obj.userData.aspect ?? 3);
        obj.scale.set(s, s / (obj.userData.aspect ?? 3), 1);
      }
    });
  }

  render(): void {
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  // ------------------------------------------------------------------ picking

  private pick(e: PointerEvent): void {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(ndc, this.camera);
    const hits = this.raycaster.intersectObjects(this.pickables, false);
    if (hits.length) {
      const sel = hits[0].object.userData.sel as Selectable | undefined;
      if (sel) this.onSelect(sel);
    }
  }

  private addStarfield(): void {
    const n = 1200;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 5e5;
      const u = Math.random() * 2 - 1;
      const th = Math.random() * Math.PI * 2;
      const s = Math.sqrt(1 - u * u);
      pos.set([r * s * Math.cos(th), r * s * Math.sin(th), r * u], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0x8893aa, size: 600 })));
  }
}
