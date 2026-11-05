// A routed fetch mock: handlers are keyed by "METHOD /path" (query string excluded).
import { vi } from "vitest";

export interface MockResponse {
  status?: number;
  body?: unknown;
}

export interface FetchCall {
  method: string;
  url: string;
  path: string;
  search: URLSearchParams;
  body: unknown;
  headers: Record<string, string>;
}

export type Handler = MockResponse | ((call: FetchCall) => MockResponse | Promise<MockResponse>);

function respond(status: number, body: unknown): Response {
  if (status === 204) return new Response(null, { status });
  const text = body === undefined ? "" : JSON.stringify(body);
  return new Response(text, { status, headers: { "Content-Type": "application/json" } });
}

export function mockFetch(routes: Record<string, Handler>) {
  const calls: FetchCall[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const parsed = new URL(url, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const call: FetchCall = {
      method,
      url,
      path: parsed.pathname,
      search: parsed.searchParams,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      headers: (init?.headers as Record<string, string> | undefined) ?? {},
    };
    calls.push(call);
    const handler = routes[`${method} ${parsed.pathname}`];
    if (!handler) return respond(404, { detail: `no mock for ${method} ${parsed.pathname}` });
    const result = typeof handler === "function" ? await handler(call) : handler;
    return respond(result.status ?? 200, result.body);
  });
  vi.stubGlobal("fetch", fn);
  return {
    fn,
    calls,
    routes,
    callsTo: (method: string, path: string) => calls.filter((call) => call.method === method && call.path === path),
  };
}
