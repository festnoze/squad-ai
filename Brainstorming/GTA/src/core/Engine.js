/**
 * Renderer + main loop.
 *
 * Rendering goes through three's WebGPURenderer. On Windows/Chrome that compiles to
 * D3D12 command buffers and runs on the discrete NVIDIA GPU, which is what we want for a
 * scene this heavy. When WebGPU is unavailable the same renderer falls back to a WebGL2
 * backend with `forceWebGL`, so there is a single code path either way.
 *
 * Simulation runs on a fixed 1/60 step; rendering runs as fast as the display allows.
 * Physics and gameplay therefore stay deterministic regardless of frame rate.
 */

import {
  WebGPURenderer, Scene, ACESFilmicToneMapping, PCFSoftShadowMap, Color,
} from 'three/webgpu';
import { FIXED_DT } from '../physics/Physics.js';

const MAX_STEPS_PER_FRAME = 5;   // beyond this we drop simulation time rather than spiral

export class Engine {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas) {
    this.canvas = canvas;
    this.scene = new Scene();
    this.scene.background = new Color(0x8fb3d9);

    this.renderer = null;
    this.backend = 'unknown';
    this.pixelRatioCap = 2;
    this.resolutionScale = 1;

    this.accumulator = 0;
    this.elapsed = 0;
    this.frame = 0;
    this.paused = false;
    this._running = false;
    this._last = 0;

    /** @type {Array<(dt:number)=>void>} */
    this.fixedCallbacks = [];
    /** @type {Array<(dt:number)=>void>} */
    this.renderCallbacks = [];
    /** Called to draw; return true if it drew, otherwise the engine draws directly. */
    this.drawOverride = null;

    this.stats = { fps: 0, ms: 0, steps: 0, drawCalls: 0, triangles: 0 };
    this._fpsAccum = 0;
    this._fpsFrames = 0;
  }

  async init() {
    const hasWebGPU = typeof navigator !== 'undefined' && !!navigator.gpu;
    // `?webgl=1` forces the WebGL2 backend. Useful for A/B-ing a rendering bug across
    // backends, and for headless capture tools that cannot read a WebGPU swap chain.
    const params = new URLSearchParams(location.search);
    const forceWebGL = !hasWebGPU || params.has('webgl');
    this.renderer = new WebGPURenderer({
      canvas: this.canvas,
      antialias: true,
      forceWebGL,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.pixelRatioCap));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = Number(params.get('exposure') ?? 0.78);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = PCFSoftShadowMap;

    await this.renderer.init();

    this.backend = this.renderer.backend?.isWebGPUBackend ? 'WebGPU (D3D12)' : 'WebGL2';
    // eslint-disable-next-line no-console
    console.info(`[Engine] backend: ${this.backend}`);

    this._onResize = () => this.resize();
    window.addEventListener('resize', this._onResize);
    this._onVisibility = () => {
      // Coming back from a hidden tab, drop the accumulated time instead of
      // simulating minutes of physics in one frame.
      if (!document.hidden) { this._last = performance.now(); this.accumulator = 0; }
    };
    document.addEventListener('visibilitychange', this._onVisibility);

    return this;
  }

  /** @param {import('three/webgpu').Camera} camera */
  setCamera(camera) { this.camera = camera; }

  onFixed(fn) { this.fixedCallbacks.push(fn); }
  onRender(fn) { this.renderCallbacks.push(fn); }

  resize() {
    const w = Math.max(1, Math.floor(window.innerWidth * this.resolutionScale));
    const h = Math.max(1, Math.floor(window.innerHeight * this.resolutionScale));
    this.renderer.setSize(w, h, false);
    // Keep the canvas filling the window even when we render at reduced resolution.
    this.canvas.style.width = '100%';
    this.canvas.style.height = '100%';
    if (this.camera) {
      this.camera.aspect = window.innerWidth / window.innerHeight;
      this.camera.updateProjectionMatrix();
    }
    this.onResized?.(w, h);
  }

  setResolutionScale(scale) {
    this.resolutionScale = Math.max(0.5, Math.min(1, scale));
    this.resize();
  }

  start() {
    if (this._running) return;
    this._running = true;
    this._last = performance.now();
    const tick = (now) => {
      if (!this._running) return;
      this._loop(now);
      this._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  }

  stop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
  }

  _loop(now) {
    const frameStart = now;
    let dt = (now - this._last) / 1000;
    this._last = now;
    // Clamp so a hitch (GC, shader compile) cannot teleport the world.
    dt = Math.min(dt, 0.25);
    this.elapsed += dt;
    this.frame++;

    if (!this.paused) {
      this.accumulator += dt;
      let steps = 0;
      while (this.accumulator >= FIXED_DT && steps < MAX_STEPS_PER_FRAME) {
        for (const fn of this.fixedCallbacks) fn(FIXED_DT);
        this.accumulator -= FIXED_DT;
        steps++;
      }
      if (steps === MAX_STEPS_PER_FRAME) this.accumulator = 0;
      this.stats.steps = steps;
    }

    for (const fn of this.renderCallbacks) fn(dt);

    const drew = this.drawOverride ? this.drawOverride() : false;
    if (!drew && this.camera) this.renderer.render(this.scene, this.camera);

    // FPS over a rolling half second.
    this._fpsAccum += dt;
    this._fpsFrames++;
    if (this._fpsAccum >= 0.5) {
      this.stats.fps = Math.round(this._fpsFrames / this._fpsAccum);
      this._fpsAccum = 0;
      this._fpsFrames = 0;
      const info = this.renderer.info?.render;
      if (info) {
        this.stats.drawCalls = info.drawCalls ?? 0;
        this.stats.triangles = info.triangles ?? 0;
      }
    }
    this.stats.ms = +(performance.now() - frameStart).toFixed(1);
  }

  dispose() {
    this.stop();
    window.removeEventListener('resize', this._onResize);
    document.removeEventListener('visibilitychange', this._onVisibility);
    this.renderer?.dispose();
  }
}
