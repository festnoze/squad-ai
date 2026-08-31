import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server runs on 5500 (Exchange holds 5173). Every /matches call, REST and WebSocket, is
// proxied to the ala API so the browser talks to one origin and there is no CORS to configure. The API
// URL defaults to the standard port 8165 and can be overridden with ALA_API (handy when 8165 is busy).
const API = process.env.ALA_API ?? "http://127.0.0.1:8165";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5500,
    proxy: {
      // REST + WebSocket replay, and the single POST /runs launch endpoint.
      "/matches": { target: API, changeOrigin: true, ws: true },
      "/runs": { target: API, changeOrigin: true },
    },
  },
});
