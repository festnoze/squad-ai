import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clientUuid,
  createProject,
  extendStory,
  getProvider,
  setProvider,
  storyChat,
  taskChat,
} from "./api";

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

describe("api — directives ciblées idempotentes (chat/extend)", () => {
  const okChat = {
    ok: true,
    status: 200,
    json: async () => ({ ok: true, entry_id: "g-srv" }),
    text: async () => "",
  };
  const okExtend = {
    ok: true,
    status: 200,
    json: async () => ({ ok: true, state: { id: "p1", name: "X" } }),
    text: async () => "",
  };

  it("storyChat envoie un entry_id client-généré et le réutilise au retry (502 -> ok)", async () => {
    const fetchMock = mockFetchSequence(proxy502, okChat);
    await storyChat("p1", "US-1", "fais ça");
    expect(fetchMock).toHaveBeenCalledTimes(2); // 502 puis retry réussi
    const firstBody = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    const retryBody = JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string);
    // Même entry_id sur les deux essais -> pas de double injection côté backend.
    expect(firstBody.entry_id).toBeTruthy();
    expect(retryBody.entry_id).toBe(firstBody.entry_id);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p1/stories/US-1/chat");
  });

  it("storyChat honore un entry_id fourni explicitement", async () => {
    const fetchMock = mockFetchSequence(okChat);
    await storyChat("p1", "US-1", "msg", "g-fixed");
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.entry_id).toBe("g-fixed");
  });

  it("taskChat poste sur la route task avec un entry_id", async () => {
    const fetchMock = mockFetchSequence(okChat);
    await taskChat("p1", "T-1", "msg");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p1/tasks/T-1/chat");
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.entry_id).toBeTruthy();
  });

  it("extendStory renvoie l'état complet et réessaie un 502 transitoire", async () => {
    const fetchMock = mockFetchSequence(proxy502, okExtend);
    const state = await extendStory("p1", "US-1", ["c1", "c2"]);
    expect(state.id).toBe("p1");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.acceptance_criteria).toEqual(["c1", "c2"]);
  });

  it("clientUuid renvoie des ids non vides et distincts", () => {
    const a = clientUuid();
    const b = clientUuid();
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
    expect(a).not.toBe(b);
  });
});
