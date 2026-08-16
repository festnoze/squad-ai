import { defineConfig } from 'vite';

export default defineConfig({
  // chemins relatifs dans le build: le jeu doit pouvoir etre servi depuis un
  // sous-chemin (la console games/arcade le sert sous /g/GTA/), pas seulement
  // depuis la racine d'une origine
  base: './',
  server: { port: 8092, strictPort: true },
  // rapier3d-compat ships its wasm inlined as base64, so no wasm plugin is needed,
  // but it must not be pre-bundled or the async init() wrapper breaks.
  optimizeDeps: { exclude: ['@dimforge/rapier3d-compat'] },
  build: { target: 'esnext', sourcemap: true },
});
