import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
const API = process.env.PMX_API ?? "http://127.0.0.1:8175";
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5510, proxy: { "/api": { target: API, changeOrigin: true } } },
});
