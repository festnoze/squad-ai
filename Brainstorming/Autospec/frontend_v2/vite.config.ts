import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The v2 API (python -m autospec.core serve) listens on 8400 and serves the built dist at "/".
export default defineConfig({
  plugins: [react()],
  server: {
    // "localhost" resolves to ::1 only on some Windows machines: bind the IPv4 loopback like the API.
    host: "127.0.0.1",
    port: 5400,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8400" },
  },
  // globals: Testing Library then unmounts what each test rendered.
  test: { environment: "jsdom", globals: true, setupFiles: ["src/test/setup.ts"] },
});
