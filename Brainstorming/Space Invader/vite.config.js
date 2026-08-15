import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: {
    port: 5310,
    open: false,
  },
  worker: {
    format: 'es',
  },
  build: {
    target: 'es2022',
    outDir: 'dist',
    sourcemap: true,
  },
});
