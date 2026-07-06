import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfirmHost, confirmAction, type ConfirmOptions } from "./ConfirmDialog";

/** confirmAction déclenche un setState du host → à envelopper dans act(). */
function openConfirm(opts: ConfirmOptions): Promise<boolean> {
  let p!: Promise<boolean>;
  act(() => {
    p = confirmAction(opts);
  });
  return p;
}

describe("ConfirmDialog (Q2)", () => {
  it("affiche titre/corps et résout true sur Confirmer", async () => {
    render(<ConfirmHost />);
    const p = openConfirm({ title: "Supprimer ?", body: "Action définitive.", danger: true });
    const accept = await screen.findByTestId("confirm-accept");
    expect(screen.getByRole("dialog", { name: "Supprimer ?" })).toBeInTheDocument();
    expect(screen.getByText("Action définitive.")).toBeInTheDocument();
    expect(accept.className).toContain("danger");
    fireEvent.click(accept);
    await expect(p).resolves.toBe(true);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("résout false sur Annuler (bouton autofocus)", async () => {
    render(<ConfirmHost />);
    const p = openConfirm({ title: "Continuer ?" });
    const cancel = await screen.findByRole("button", { name: /Cancel|Annuler/ });
    expect(cancel).toHaveFocus();
    fireEvent.click(cancel);
    await expect(p).resolves.toBe(false);
  });

  it("résout false sur Escape", async () => {
    render(<ConfirmHost />);
    const p = openConfirm({ title: "Continuer ?" });
    await screen.findByTestId("confirm-accept");
    fireEvent.keyDown(document, { key: "Escape" });
    await expect(p).resolves.toBe(false);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("résout true sur Entrée dans le dialogue", async () => {
    render(<ConfirmHost />);
    const p = openConfirm({ title: "Continuer ?" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Enter" });
    await expect(p).resolves.toBe(true);
  });
});
