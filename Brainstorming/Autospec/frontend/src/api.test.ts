import { afterEach, describe, expect, it, vi } from "vitest";
import { createProject, getProvider, setProvider } from "./api";

const okProvider = {
  ok: true,
  status: 200,
  json: async () => ({ provider: "claude", model: "opus", available: [], models: {} }),
  text: async () => "",
};
const okCreate = {
  ok: true,
  status: 200,
  json: async () => ({ id: "p1", state: {} }),
  text: async () => "",
};
const proxy502 = {
  ok: false,
  status: 502,
  json: async () => ({}),
  text: async () => "proxy error: ECONNRESET",
};

function mockFetchSequence(...responses: unknown[]) {
  const fn = vi.fn();
  responses.forEach((r) => fn.mockResolvedValueOnce(r));
  // Any extra call resolves to the last response.
  fn.mockResolvedValue(responses[responses.length - 1]);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api — retry des appels idempotents (provider)", () => {
  it("setProvider réessaie un 502 transitoire du proxy puis réussit", async () => {
    const fetchMock = mockFetchSequence(proxy502, okProvider);
    const info = await setProvider("claude", "opus");
    expect(info.provider).toBe("claude");
    expect(fetchMock).toHaveBeenCalledTimes(2); // 1 échec + 1 retry réussi
  });

  it("setProvider abandonne après épuisement des retries (502 persistant)", async () => {
    const fetchMock = mockFetchSequence(proxy502, proxy502, proxy502, proxy502);
    await expect(setProvider("openai", "gpt-4.1")).rejects.toThrow(/502/);
    expect(fetchMock).toHaveBeenCalledTimes(3); // appel initial + 2 retries
  });

  it("getProvider réessaie aussi un 502 transitoire", async () => {
    const fetchMock = mockFetchSequence(proxy502, okProvider);
    await getProvider();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("createProject (NON idempotent) ne réessaie PAS un 502 — pas de double création", async () => {
    const fetchMock = mockFetchSequence(proxy502);
    await expect(createProject("un but", "Nom", false)).rejects.toThrow(/502/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
