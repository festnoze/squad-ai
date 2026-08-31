import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server on 5510; proxy the API paths to pmx on 8175. Override with PMX_API if 8175 is busy.
const API = process.env.PMX_API ?? "http://127.0.0.1:8175";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5510,
    proxy: {
      "/markets": { target: API, changeOrigin: true },
      "/agents": { target: API, changeOrigin: true },
      "/tournament": { target: API, changeOrigin: true },
      "/walkforward": { target: API, changeOrigin: true },
    },
  },
});
