/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.VITE_BACKEND_PORT ?? "8100";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5183,
    proxy: {
      "/api": `http://127.0.0.1:${backendPort}`,
      "/ws": { target: `ws://127.0.0.1:${backendPort}`, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
});
