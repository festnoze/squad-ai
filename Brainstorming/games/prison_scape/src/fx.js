import * as THREE from 'three';

const MAX_PARTICLES = 900;
const MAX_TRACERS = 48;
const MAX_DECALS = 120;

/**
 * Pooled visual effects: sparks, blood, dust, glass, bullet tracers, decals
 * and floating damage/status text. Everything is allocated once at boot and
 * recycled, so the game never garbage-collects mid-firefight.
 */
export class Effects {
  constructor(scene) {
    this.scene = scene;
    this.time = 0;

    // ------------------------------------------------------------ particles
    const geo = new THREE.BufferGeometry();
    this.pPos = new Float32Array(MAX_PARTICLES * 3);
    this.pCol = new Float32Array(MAX_PARTICLES * 3);
    this.pSize = new Float32Array(MAX_PARTICLES);
    geo.setAttribute('position', new THREE.BufferAttribute(this.pPos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(this.pCol, 3));
    geo.setAttribute('size', new THREE.BufferAttribute(this.pSize, 1));
    geo.setDrawRange(0, 0);

    const mat = new THREE.ShaderMaterial({
      uniforms: {},
      vertexShader: `
        attribute float size;
        varying vec3 vColor;
        void main() {
          vColor = color;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (300.0 / max(1.0, -mv.z));
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        varying vec3 vColor;
        void main() {
          vec2 d = gl_PointCoord - vec2(0.5);
          float a = 1.0 - smoothstep(0.22, 0.5, length(d));
          if (a <= 0.01) discard;
          gl_FragColor = vec4(vColor, a);
        }`,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
    });
    this.points = new THREE.Points(geo, mat);
    this.points.frustumCulled = false;
    this.points.renderOrder = 4;
    scene.add(this.points);

    this.particles = [];
    for (let i = 0; i < MAX_PARTICLES; i++) {
      this.particles.push({
        alive: false,
        x: 0, y: 0, z: 0,
        vx: 0, vy: 0, vz: 0,
        life: 0, maxLife: 1,
        size: 1, drag: 0.98, gravity: -9,
        r: 1, g: 1, b: 1,
        fade: true,
      });
    }
    this.pCount = 0;

    // -------------------------------------------------------------- tracers
    this.tracers = [];
    const tracerGeo = new THREE.BufferGeometry();
    tracerGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    for (let i = 0; i < MAX_TRACERS; i++) {
      const m = new THREE.Line(
        tracerGeo.clone(),
        new THREE.LineBasicMaterial({
          color: 0xffd27a, transparent: true, opacity: 0,
          blending: THREE.AdditiveBlending, depthWrite: false,
        })
      );
      m.frustumCulled = false;
      m.visible = false;
      m.renderOrder = 3;
      scene.add(m);
      this.tracers.push({ mesh: m, life: 0, maxLife: 0.09 });
    }

    // --------------------------------------------------------------- decals
    this.decals = [];
    const decalGeo = new THREE.PlaneGeometry(1, 1);
    for (let i = 0; i < MAX_DECALS; i++) {
      const m = new THREE.Mesh(decalGeo, new THREE.MeshBasicMaterial({
        color: 0x0b0b0c, transparent: true, opacity: 0,
        depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4,
      }));
      m.visible = false;
      m.renderOrder = 2;
      scene.add(m);
      this.decals.push({ mesh: m, used: false });
    }
    this.decalCursor = 0;

    // ---------------------------------------------------------- muzzle glow
    this.muzzleLight = new THREE.PointLight(0xffcf80, 0, 14, 2);
    scene.add(this.muzzleLight);
    this._muzzleTimer = 0;
  }

  _spawn(cfg) {
    for (let i = 0; i < MAX_PARTICLES; i++) {
      const p = this.particles[i];
      if (p.alive) continue;
      Object.assign(p, cfg);
      p.alive = true;
      p.life = 0;
      return p;
    }
    return null;
  }

  /** Bright orange sparks bouncing off a hard surface. */
  sparks(pos, normal, count = 14, color = [1.0, 0.72, 0.28]) {
    for (let i = 0; i < count; i++) {
      const speed = 3 + Math.random() * 9;
      this._spawn({
        x: pos.x, y: pos.y, z: pos.z,
        vx: (normal.x + (Math.random() - 0.5) * 1.4) * speed,
        vy: (normal.y + (Math.random() - 0.5) * 1.4 + 0.4) * speed,
        vz: (normal.z + (Math.random() - 0.5) * 1.4) * speed,
        maxLife: 0.25 + Math.random() * 0.5,
        size: 0.9 + Math.random() * 1.4,
        drag: 0.93, gravity: -16,
        r: color[0], g: color[1], b: color[2], fade: true,
      });
    }
  }

  /** Grey puff of pulverised concrete. */
  dust(pos, count = 8, spread = 1.2) {
    for (let i = 0; i < count; i++) {
      this._spawn({
        x: pos.x + (Math.random() - 0.5) * 0.3,
        y: pos.y + (Math.random() - 0.5) * 0.3,
        z: pos.z + (Math.random() - 0.5) * 0.3,
        vx: (Math.random() - 0.5) * spread,
        vy: Math.random() * spread * 0.8,
        vz: (Math.random() - 0.5) * spread,
        maxLife: 0.6 + Math.random() * 0.7,
        size: 2.5 + Math.random() * 3.5,
        drag: 0.9, gravity: -0.6,
        r: 0.38, g: 0.38, b: 0.36, fade: true,
      });
    }
  }

  blood(pos, dir, count = 16) {
    for (let i = 0; i < count; i++) {
      const speed = 1.5 + Math.random() * 5;
      this._spawn({
        x: pos.x, y: pos.y, z: pos.z,
        vx: (dir.x + (Math.random() - 0.5) * 1.2) * speed,
        vy: (dir.y + (Math.random() - 0.5) * 1.2 + 0.5) * speed,
        vz: (dir.z + (Math.random() - 0.5) * 1.2) * speed,
        maxLife: 0.35 + Math.random() * 0.5,
        size: 1.6 + Math.random() * 2.4,
        drag: 0.9, gravity: -13,
        r: 0.55, g: 0.05, b: 0.06, fade: true,
      });
    }
  }

  /** Shattered camera lens: white-blue shards plus an electrical flash. */
  glass(pos, count = 22) {
    for (let i = 0; i < count; i++) {
      const speed = 2 + Math.random() * 8;
      this._spawn({
        x: pos.x, y: pos.y, z: pos.z,
        vx: (Math.random() - 0.5) * speed,
        vy: (Math.random() - 0.2) * speed,
        vz: (Math.random() - 0.5) * speed,
        maxLife: 0.5 + Math.random() * 0.8,
        size: 0.8 + Math.random() * 1.6,
        drag: 0.95, gravity: -14,
        r: 0.72, g: 0.9, b: 1.0, fade: true,
      });
    }
    this.sparks(pos, new THREE.Vector3(0, 1, 0), 18, [0.6, 0.85, 1.0]);
  }

  /** Rising smoke column, used by dead cameras and the intro fires. */
  smoke(pos, count = 6) {
    for (let i = 0; i < count; i++) {
      this._spawn({
        x: pos.x + (Math.random() - 0.5) * 0.25,
        y: pos.y,
        z: pos.z + (Math.random() - 0.5) * 0.25,
        vx: (Math.random() - 0.5) * 0.3,
        vy: 0.5 + Math.random() * 0.7,
        vz: (Math.random() - 0.5) * 0.3,
        maxLife: 1.2 + Math.random() * 1.4,
        size: 3 + Math.random() * 5,
        drag: 0.985, gravity: 0.25,
        r: 0.16, g: 0.16, b: 0.17, fade: true,
      });
    }
  }

  tracer(from, to) {
    for (const t of this.tracers) {
      if (t.life > 0) continue;
      const arr = t.mesh.geometry.attributes.position.array;
      arr[0] = from.x; arr[1] = from.y; arr[2] = from.z;
      arr[3] = to.x; arr[4] = to.y; arr[5] = to.z;
      t.mesh.geometry.attributes.position.needsUpdate = true;
      t.mesh.material.opacity = 0.85;
      t.mesh.visible = true;
      t.life = t.maxLife;
      return;
    }
  }

  /** Persistent scorch mark. Oldest decal is recycled once the pool is full. */
  decal(pos, normal, size = 0.28, color = 0x0b0b0c, opacity = 0.85) {
    const d = this.decals[this.decalCursor];
    this.decalCursor = (this.decalCursor + 1) % MAX_DECALS;
    d.mesh.position.copy(pos).addScaledVector(normal, 0.012);
    d.mesh.lookAt(pos.clone().add(normal));
    d.mesh.scale.setScalar(size * (0.8 + Math.random() * 0.5));
    d.mesh.rotateZ(Math.random() * Math.PI * 2);
    d.mesh.material.color.setHex(color);
    d.mesh.material.opacity = opacity;
    d.mesh.visible = true;
  }

  muzzleFlash(pos, strength = 1) {
    this.muzzleLight.position.copy(pos);
    this.muzzleLight.intensity = 9 * strength;
    this._muzzleTimer = 0.055;
    for (let i = 0; i < 5; i++) {
      this._spawn({
        x: pos.x, y: pos.y, z: pos.z,
        vx: (Math.random() - 0.5) * 3,
        vy: (Math.random() - 0.5) * 3,
        vz: (Math.random() - 0.5) * 3,
        maxLife: 0.06 + Math.random() * 0.06,
        size: 5 + Math.random() * 5,
        drag: 0.8, gravity: 0,
        r: 1.0, g: 0.85, b: 0.5, fade: true,
      });
    }
  }

  update(dt) {
    this.time += dt;

    // particles
    let n = 0;
    for (let i = 0; i < MAX_PARTICLES; i++) {
      const p = this.particles[i];
      if (!p.alive) continue;
      p.life += dt;
      if (p.life >= p.maxLife) {
        p.alive = false;
        continue;
      }
      p.vy += p.gravity * dt;
      const d = Math.pow(p.drag, dt * 60);
      p.vx *= d; p.vy *= d; p.vz *= d;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.z += p.vz * dt;
      if (p.y < 0.02 && p.gravity < 0) {
        p.y = 0.02;
        p.vy *= -0.25;
        p.vx *= 0.6;
        p.vz *= 0.6;
      }
      const k = p.fade ? 1 - p.life / p.maxLife : 1;
      const j = n * 3;
      this.pPos[j] = p.x; this.pPos[j + 1] = p.y; this.pPos[j + 2] = p.z;
      this.pCol[j] = p.r * k; this.pCol[j + 1] = p.g * k; this.pCol[j + 2] = p.b * k;
      this.pSize[n] = p.size * (0.5 + 0.5 * k);
      n++;
    }
    this.pCount = n;
    this.points.geometry.setDrawRange(0, n);
    this.points.geometry.attributes.position.needsUpdate = true;
    this.points.geometry.attributes.color.needsUpdate = true;
    this.points.geometry.attributes.size.needsUpdate = true;

    // tracers
    for (const t of this.tracers) {
      if (t.life <= 0) continue;
      t.life -= dt;
      if (t.life <= 0) {
        t.mesh.visible = false;
        t.mesh.material.opacity = 0;
      } else {
        t.mesh.material.opacity = 0.85 * (t.life / t.maxLife);
      }
    }

    // muzzle light
    if (this._muzzleTimer > 0) {
      this._muzzleTimer -= dt;
      if (this._muzzleTimer <= 0) this.muzzleLight.intensity = 0;
      else this.muzzleLight.intensity *= 0.82;
    }
  }

  /** Wipe every live effect - used when a run restarts. */
  reset() {
    for (const p of this.particles) p.alive = false;
    this.pCount = 0;
    this.points.geometry.setDrawRange(0, 0);
    for (const t of this.tracers) {
      t.life = 0;
      t.mesh.visible = false;
    }
    for (const d of this.decals) {
      d.mesh.visible = false;
      d.mesh.material.opacity = 0;
    }
    this.muzzleLight.intensity = 0;
    this._muzzleTimer = 0;
  }
}
