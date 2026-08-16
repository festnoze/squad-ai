import * as THREE from 'three';

const UP = new THREE.Vector3(0, 1, 0);
const FWD = new THREE.Vector3(0, 0, 1);
const _q = new THREE.Quaternion();
const _v = new THREE.Vector3();

/** A pool of textured point sprites with velocity, gravity and fade. */
class ParticleField {
  constructor(scene, texture, opts = {}) {
    this.count = opts.count ?? 200;
    this.gravity = opts.gravity ?? -9;
    this.drag = opts.drag ?? 1.6;
    this.baseSize = opts.size ?? 0.12;
    this.positions = new Float32Array(this.count * 3);
    this.sizes = new Float32Array(this.count);
    this.alphas = new Float32Array(this.count);
    this.vel = new Float32Array(this.count * 3);
    this.life = new Float32Array(this.count);
    this.maxLife = new Float32Array(this.count);
    this.cursor = 0;

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    geo.setAttribute('aSize', new THREE.BufferAttribute(this.sizes, 1));
    geo.setAttribute('aAlpha', new THREE.BufferAttribute(this.alphas, 1));

    const mat = new THREE.ShaderMaterial({
      uniforms: {
        uTex: { value: texture },
        uColor: { value: new THREE.Color(opts.color ?? 0xffffff) },
        uScale: { value: 600 },
      },
      vertexShader: /* glsl */ `
        attribute float aSize;
        attribute float aAlpha;
        varying float vAlpha;
        uniform float uScale;
        void main() {
          vAlpha = aAlpha;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = aSize * uScale / max(0.001, -mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform sampler2D uTex;
        uniform vec3 uColor;
        varying float vAlpha;
        void main() {
          vec4 t = texture2D(uTex, gl_PointCoord);
          gl_FragColor = vec4(uColor * t.rgb, t.a * vAlpha);
          if (gl_FragColor.a < 0.01) discard;
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: opts.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    });

    this.points = new THREE.Points(geo, mat);
    this.points.frustumCulled = false;
    this.points.renderOrder = 5;
    scene.add(this.points);
    this.geo = geo;
  }

  emit(origin, dir, opts = {}) {
    const n = opts.count ?? 8;
    const speed = opts.speed ?? 6;
    const spread = opts.spread ?? 0.7;
    const life = opts.life ?? 0.6;
    const size = opts.size ?? this.baseSize;
    for (let k = 0; k < n; k++) {
      const i = this.cursor;
      this.cursor = (this.cursor + 1) % this.count;
      const i3 = i * 3;
      this.positions[i3] = origin.x;
      this.positions[i3 + 1] = origin.y;
      this.positions[i3 + 2] = origin.z;
      const sp = speed * (0.35 + Math.random() * 0.9);
      this.vel[i3] = (dir.x + (Math.random() - 0.5) * spread * 2) * sp;
      this.vel[i3 + 1] = (dir.y + (Math.random() - 0.5) * spread * 2) * sp;
      this.vel[i3 + 2] = (dir.z + (Math.random() - 0.5) * spread * 2) * sp;
      const l = life * (0.6 + Math.random() * 0.8);
      this.life[i] = l;
      this.maxLife[i] = l;
      this.sizes[i] = size * (0.6 + Math.random() * 0.9);
      this.alphas[i] = 1;
    }
  }

  update(dt) {
    let alive = false;
    for (let i = 0; i < this.count; i++) {
      if (this.life[i] <= 0) continue;
      alive = true;
      this.life[i] -= dt;
      const i3 = i * 3;
      if (this.life[i] <= 0) {
        this.alphas[i] = 0;
        this.positions[i3 + 1] = -9999;
        continue;
      }
      const d = Math.max(0, 1 - this.drag * dt);
      this.vel[i3] *= d;
      this.vel[i3 + 1] = this.vel[i3 + 1] * d + this.gravity * dt;
      this.vel[i3 + 2] *= d;
      this.positions[i3] += this.vel[i3] * dt;
      this.positions[i3 + 1] += this.vel[i3 + 1] * dt;
      this.positions[i3 + 2] += this.vel[i3 + 2] * dt;
      this.alphas[i] = Math.min(1, this.life[i] / (this.maxLife[i] * 0.6));
    }
    if (alive) {
      this.geo.attributes.position.needsUpdate = true;
      this.geo.attributes.aAlpha.needsUpdate = true;
      this.geo.attributes.aSize.needsUpdate = true;
    }
  }

  reset() {
    this.life.fill(0);
    this.alphas.fill(0);
    for (let i = 0; i < this.count; i++) this.positions[i * 3 + 1] = -9999;
    this.geo.attributes.position.needsUpdate = true;
    this.geo.attributes.aAlpha.needsUpdate = true;
  }
}

/**
 * All transient visuals: bullet tracers, impact sparks, dust, blood,
 * bullet holes and drifting ash.
 */
export class Effects {
  constructor(scene, tex) {
    this.scene = scene;
    this.tex = tex;

    this.sparks = new ParticleField(scene, tex.flash, {
      count: 320, color: 0xffb45a, size: 0.055, gravity: -14, additive: true, drag: 2.2,
    });
    this.dust = new ParticleField(scene, tex.smoke, {
      count: 260, color: 0x9d9384, size: 0.5, gravity: -0.7, drag: 2.6,
    });
    this.blood = new ParticleField(scene, tex.blood, {
      count: 260, color: 0xb01818, size: 0.13, gravity: -11, drag: 1.4,
    });

    // --- tracer pool ---
    this.tracers = [];
    const tracerGeo = new THREE.CylinderGeometry(0.018, 0.018, 1, 5, 1, true);
    tracerGeo.translate(0, 0.5, 0);
    const tracerMat = new THREE.MeshBasicMaterial({
      color: 0xffd190, transparent: true, opacity: 0.9,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    for (let i = 0; i < 20; i++) {
      const m = new THREE.Mesh(tracerGeo, tracerMat.clone());
      m.visible = false;
      m.frustumCulled = false;
      m.renderOrder = 4;
      scene.add(m);
      this.tracers.push({ mesh: m, life: 0, maxLife: 0.07 });
    }
    this.tracerCursor = 0;

    // --- bullet hole decal pool ---
    this.decals = [];
    const decalGeo = new THREE.PlaneGeometry(1, 1);
    const decalMat = new THREE.MeshBasicMaterial({
      map: tex.hole, transparent: true, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4,
    });
    for (let i = 0; i < 80; i++) {
      const m = new THREE.Mesh(decalGeo, decalMat);
      m.visible = false;
      m.renderOrder = 3;
      scene.add(m);
      this.decals.push(m);
    }
    this.decalCursor = 0;

    // --- impact flash lights (cheap, short lived) ---
    this.flashLights = [];
    for (let i = 0; i < 3; i++) {
      const l = new THREE.PointLight(0xffa040, 0, 9, 2);
      l.visible = false;
      scene.add(l);
      this.flashLights.push({ light: l, life: 0 });
    }
    this.flashCursor = 0;
  }

  tracer(from, to) {
    const t = this.tracers[this.tracerCursor];
    this.tracerCursor = (this.tracerCursor + 1) % this.tracers.length;
    const dir = _v.copy(to).sub(from);
    const len = dir.length();
    if (len < 0.01) return;
    dir.multiplyScalar(1 / len);
    t.mesh.position.copy(from);
    t.mesh.quaternion.setFromUnitVectors(UP, dir);
    t.mesh.scale.set(1, len, 1);
    t.mesh.visible = true;
    t.mesh.material.opacity = 0.9;
    t.life = t.maxLife;
  }

  /** kind: 'concrete' | 'metal' | 'flesh' */
  impact(point, normal, kind = 'concrete') {
    if (kind === 'flesh') {
      this.blood.emit(point, normal, { count: 8, speed: 5, spread: 0.7, life: 0.45, size: 0.09 });
      return;
    }
    this.sparks.emit(point, normal, {
      count: kind === 'metal' ? 14 : 8,
      speed: kind === 'metal' ? 9 : 5.5,
      spread: 0.85, life: 0.35, size: 0.05,
    });
    this.dust.emit(point, normal, { count: 5, speed: 1.6, spread: 0.9, life: 0.9, size: 0.55 });
    this.decal(point, normal);
    this.pointFlash(point, kind === 'metal' ? 5 : 2.4);
  }

  decal(point, normal) {
    const m = this.decals[this.decalCursor];
    this.decalCursor = (this.decalCursor + 1) % this.decals.length;
    m.position.copy(point).addScaledVector(normal, 0.012);
    m.quaternion.setFromUnitVectors(FWD, normal);
    m.rotateZ(Math.random() * Math.PI * 2);
    const s = 0.22 + Math.random() * 0.14;
    m.scale.set(s, s, s);
    m.visible = true;
  }

  pointFlash(pos, intensity = 4) {
    const f = this.flashLights[this.flashCursor];
    this.flashCursor = (this.flashCursor + 1) % this.flashLights.length;
    f.light.position.copy(pos);
    f.light.intensity = intensity;
    f.light.visible = true;
    f.life = 0.06;
  }

  bloodBurst(point, dir, big = false) {
    // Kept deliberately lean: a kill at arm's length must not blank the screen.
    this.blood.emit(point, dir, {
      count: big ? 20 : 10, speed: big ? 8 : 5,
      spread: big ? 0.9 : 0.65, life: big ? 0.7 : 0.5, size: big ? 0.13 : 0.09,
    });
  }

  smoke(point, dir, count = 6) {
    this.dust.emit(point, dir, { count, speed: 1.2, spread: 0.8, life: 1.3, size: 0.7 });
  }

  update(dt) {
    this.sparks.update(dt);
    this.dust.update(dt);
    this.blood.update(dt);

    for (let i = 0; i < this.tracers.length; i++) {
      const t = this.tracers[i];
      if (t.life <= 0) continue;
      t.life -= dt;
      if (t.life <= 0) {
        t.mesh.visible = false;
      } else {
        t.mesh.material.opacity = 0.9 * (t.life / t.maxLife);
      }
    }
    for (let i = 0; i < this.flashLights.length; i++) {
      const f = this.flashLights[i];
      if (f.life <= 0) continue;
      f.life -= dt;
      if (f.life <= 0) {
        f.light.visible = false;
        f.light.intensity = 0;
      } else {
        f.light.intensity *= 0.72;
      }
    }
  }

  reset() {
    this.sparks.reset();
    this.dust.reset();
    this.blood.reset();
    for (const t of this.tracers) { t.life = 0; t.mesh.visible = false; }
    for (const d of this.decals) d.visible = false;
    for (const f of this.flashLights) { f.life = 0; f.light.visible = false; f.light.intensity = 0; }
  }
}
