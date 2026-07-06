import { afterEach, describe, expect, it, vi } from "vitest";
import { copyText } from "./clipboard";
import { subscribeToasts } from "./toast";

describe("copyText (Q7)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("copie via navigator.clipboard et émet un toast succès", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const toasts: string[] = [];
    const off = subscribeToasts((t) => toasts.push(t.level));
    await expect(copyText("hello")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
    expect(toasts).toEqual(["success"]);
    off();
  });

  it("échec de copie → toast erreur et false", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const toasts: string[] = [];
    const off = subscribeToasts((t) => toasts.push(t.level));
    await expect(copyText("hello")).resolves.toBe(false);
    expect(toasts).toEqual(["error"]);
    off();
  });
});
