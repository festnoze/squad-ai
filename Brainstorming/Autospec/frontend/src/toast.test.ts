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

  it("R6 : l'action optionnelle est transmise telle quelle aux abonnés", () => {
    const fn = vi.fn();
    const onClick = vi.fn();
    const off = subscribeToasts(fn);
    notify("success", "Supprimée", "Corps", { label: "Annuler", onClick });
    expect(fn).toHaveBeenCalledWith({
      level: "success",
      title: "Supprimée",
      body: "Corps",
      action: { label: "Annuler", onClick },
    });
    const ev = fn.mock.calls[0][0] as { action: { onClick: () => void } };
    ev.action.onClick();
    expect(onClick).toHaveBeenCalledTimes(1);
    off();
  });

  it("R6 : sans action, l'évènement ne porte pas la clé `action`", () => {
    const fn = vi.fn();
    const off = subscribeToasts(fn);
    notify("info", "Simple");
    expect(fn.mock.calls[0][0]).not.toHaveProperty("action");
    off();
  });
});
