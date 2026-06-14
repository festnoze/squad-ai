/// <reference types="vitest/config" />
import http from "node:http";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.VITE_BACKEND_PORT ?? "8100";
const apiTarget = `http://127.0.0.1:${backendPort}`;

// Force a FRESH connection per upstream request: reusing a pooled keep-alive
// socket that uvicorn already half-closed (idle keep-alive timeout) is the
// classic Windows-loopback failure mode — the proxy writes to a dead socket and
// then waits forever (no error, no response), wedging the request. A fresh
// connection sidesteps the stale socket entirely.
const noKeepAliveAgent = new http.Agent({ keepAlive: false, maxSockets: 64 });

// Hard backstop so a stuck upstream connection can NEVER hang forever (which
// otherwise leaves the UI stuck in its "busy" state, e.g. a wedged create
// modal). Generous enough not to cut off legitimately slow ops (zip export,
// doc generation). On expiry http-proxy emits an error -> handled below.
const PROXY_TIMEOUT_MS = 30_000;

// Defense-in-depth for the dev proxy. Talking to a single-threaded uvicorn over
// Windows loopback intermittently fails to establish a *fresh* connection
// (~ETIMEDOUT/ECONNREFUSED) before the request ever reaches the backend — visible
// in chat as `http proxy error: ETIMEDOUT on POST …`. We transparently retry.
//
// Safety: a CONNECT-PHASE failure (error stack `TCPConnectWrap.afterConnect`,
// codes below) means the request was never delivered, so retrying any method —
// including POST — cannot double-execute. A MID-STREAM reset may already have
// been processed server-side, so we only retry those for idempotent methods.
// (The real fix is backend-side: never block the event loop. This smooths over
// the residual Windows-loopback transients.)
const CONNECT_PHASE_CODES = new Set([
  "ETIMEDOUT",
  "ECONNREFUSED",
  "EHOSTUNREACH",
  "ENETUNREACH",
]);
const MIDSTREAM_CODES = new Set(["ECONNRESET", "EPIPE"]);
const IDEMPOTENT_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 150;

/** A proxy route to the backend that retries connection-level failures. */
function retryingProxy(target: string) {
  return {
    target,
    agent: noKeepAliveAgent,
    proxyTimeout: PROXY_TIMEOUT_MS,
    configure: (proxy: any, options: any) => {
      const attempts = new WeakMap<object, number>();
      // Vite registers its OWN 'error' handler right after calling configure()
      // (it answers with an immediate 500). Replace it on the next tick with a
      // retry-capable one, so a request we retry isn't also failed by Vite.
      setImmediate(() => {
        proxy.removeAllListeners("error");
        proxy.on("error", (err: NodeJS.ErrnoException, req: any, res: any) => {
          const code = err.code ?? "";
          const method = String(req?.method ?? "GET").toUpperCase();
          const isHttpRes = res && typeof res.writeHead === "function";
          const n = attempts.get(req) ?? 0;

          // Connect-phase failure -> not delivered -> safe to retry any method.
          // Mid-stream reset -> only safe for idempotent methods.
          const retriableCode =
            CONNECT_PHASE_CODES.has(code) ||
            (MIDSTREAM_CODES.has(code) && IDEMPOTENT_METHODS.has(method));

          const canRetry =
            retriableCode &&
            n < MAX_RETRIES &&
            isHttpRes &&
            !res.headersSent &&
            !res.writableEnded;

          if (canRetry) {
            attempts.set(req, n + 1);
            setTimeout(() => {
              try {
                proxy.web(req, res, options);
              } catch {
                if (!res.headersSent) {
                  res.writeHead(502, { "Content-Type": "text/plain" });
                  res.end(`proxy error: ${code || err.message}`);
                }
              }
            }, RETRY_DELAY_MS);
            return;
          }

          // Out of retries (or not retriable): log once and answer cleanly
          // rather than leaving the socket hanging.
          console.error(
            `[vite] api proxy error: ${code || err.message} on ${method} ${req?.url ?? ""}` +
              (n > 0 ? ` (gave up after ${n} ${n === 1 ? "retry" : "retries"})` : ""),
          );
          if (isHttpRes && !res.headersSent) {
            res.writeHead(502, { "Content-Type": "text/plain" });
            res.end(`proxy error: ${code || err.message}`);
          } else if (res && typeof res.destroy === "function") {
            res.destroy(); // WebSocket / raw socket
          }
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5183,
    proxy: {
      "/api": retryingProxy(apiTarget),
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
