/// <reference types="vitest/config" />
import http from "node:http";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.VITE_BACKEND_PORT ?? "8100";
const apiTarget = `http://127.0.0.1:${backendPort}`;

// REUSE upstream connections (keep-alive). Forcing a fresh connection per request
// maximizes loopback connect attempts, and on Windows each fresh connect has a
// small chance of ETIMEDOUT/ECONNRESET — so per-request churn turns a rare glitch
// into a frequent one (the `ECONNRESET on POST /api/provider` / `ws ETIMEDOUT`
// noise). A pooled socket that the backend closed surfaces a fast reset on reuse
// (retried below), not a hang, on loopback where FIN/RST is delivered promptly.
const keepAliveAgent = new http.Agent({
  keepAlive: true,
  keepAliveMsecs: 1000,
  maxSockets: 64,
});

// Hard backstop so a stuck upstream connection can NEVER hang forever (which
// otherwise leaves the UI stuck in its "busy" state, e.g. a wedged create modal).
// Bounds the rare half-open stale socket; still generous for slow dev ops.
const PROXY_TIMEOUT_MS = 12_000;

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
    agent: keepAliveAgent,
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

// SSE stream (`/api/stream`): a long-lived response that stays idle between
// events. It must NOT inherit `/api`'s PROXY_TIMEOUT (that would kill the stream
// mid-flight) and needs no retry — EventSource reconnects natively, and the
// backend replays missed events via Last-Event-ID. We only swallow connect
// errors so a backend restart doesn't spam the console; the browser reconnects.
function streamProxy(target: string) {
  return {
    target,
    agent: keepAliveAgent,
    // No proxyTimeout: an idle SSE stream between two events must not be cut.
    configure: (proxy: any) => {
      setImmediate(() => {
        proxy.removeAllListeners("error");
        proxy.on("error", (_err: NodeJS.ErrnoException, _req: any, res: any) => {
          if (res && typeof res.destroy === "function") res.destroy();
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
      // `/api/stream` first: more specific, must win over the generic `/api`.
      "/api/stream": streamProxy(apiTarget),
      "/api": retryingProxy(apiTarget),
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
