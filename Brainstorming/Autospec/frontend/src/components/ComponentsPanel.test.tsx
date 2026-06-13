import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ComponentsPanel } from "./ComponentsPanel";
import { ProductComponent } from "../types";

function makeComponent(overrides: Partial<ProductComponent> = {}): ProductComponent {
  return {
    id: "backend",
    kind: "backend",
    name: "API backend",
    technology: "Python + FastAPI",
    rationale: "",
    optional: false,
    status: "approved",
    ...overrides,
  };
}

describe("ComponentsPanel (E3/E4)", () => {
  it("ne rend rien sans composants", () => {
    const { container } = render(
      <ComponentsPanel components={[]} onUpdate={vi.fn()} onSetup={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("liste les composants avec leur statut", () => {
    render(
      <ComponentsPanel
        components={[
          makeComponent(),
          makeComponent({ id: "db", kind: "database", name: "BDD", technology: "PostgreSQL", optional: true, status: "proposed" }),
        ]}
        onUpdate={vi.fn()}
        onSetup={vi.fn()}
      />,
    );
    expect(screen.getByText(/API backend/)).toBeInTheDocument();
    expect(screen.getByText("approuvé")).toBeInTheDocument();
    expect(screen.getByText("proposé")).toBeInTheDocument();
    expect(screen.getByText(/\(optionnel\)/)).toBeInTheDocument();
  });

  it("✓ approuve un composant proposé (onUpdate reçoit la liste à jour)", () => {
    const onUpdate = vi.fn();
    render(
      <ComponentsPanel
        components={[makeComponent({ status: "proposed" })]}
        onUpdate={onUpdate}
        onSetup={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTitle("Approuver ce composant"));
    expect(onUpdate).toHaveBeenCalledWith([
      expect.objectContaining({ id: "backend", status: "approved" }),
    ]);
  });

  it("le bouton de setup est désactivé sans composant approuvé", () => {
    render(
      <ComponentsPanel
        components={[makeComponent({ status: "proposed" })]}
        onUpdate={vi.fn()}
        onSetup={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Créer les composants/ }),
    ).toBeDisabled();
  });

  it("le bouton de setup appelle onSetup quand un composant est approuvé", () => {
    const onSetup = vi.fn();
    render(
      <ComponentsPanel
        components={[makeComponent()]}
        onUpdate={vi.fn()}
        onSetup={onSetup}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Créer les composants/ }));
    expect(onSetup).toHaveBeenCalledTimes(1);
  });
});
