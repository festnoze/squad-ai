import { defineConfig } from 'vite';

export default defineConfig({
  server: { port: 8092, strictPort: true },
  // rapier3d-compat ships its wasm inlined as base64, so no wasm plugin is needed,
  // but it must not be pre-bundled or the async init() wrapper breaks.
  optimizeDeps: { exclude: ['@dimforge/rapier3d-compat'] },
  build: { target: 'esnext', sourcemap: true },
});
