import { describe, expect, it, vi } from "vitest";
import { notify, subscribeToasts } from "./toast";

describe("toast bus (Q0)", () => {
  it("notifie les abonnés avec level/title/body", () => {
    const fn = vi.fn();
    const off = subscribeToasts(fn);
    notify("success", "Titre", "Corps");
    expect(fn).toHaveBeenCalledWith({ level: "success", title: "Titre", body: "Corps" });
    off();
  });

  it("body vide par défaut, et désabonnement effectif", () => {
    const fn = vi.fn();
    const off = subscribeToasts(fn);
    notify("info", "Sans corps");
    expect(fn).toHaveBeenCalledWith({ level: "info", title: "Sans corps", body: "" });
    off();
    notify("info", "Après désabonnement");
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
