import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LanguagePanel } from "./LanguagePanel";

describe("LanguagePanel (L2)", () => {
  it("ne s'affiche pas tant que l'analyse n'est pas faite", () => {
    const { container } = render(<LanguagePanel onSet={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("affiche langage recommandé + scores + rationale", () => {
    render(
      <LanguagePanel
        language="go"
        complexity={3}
        criticality={2}
        rationale="Compromis débit de boucle."
        onSet={vi.fn()}
      />,
    );
    expect(screen.getByText("3/5")).toBeInTheDocument();
    expect(screen.getByText("2/5")).toBeInTheDocument();
    expect(screen.getByText(/Compromis débit/)).toBeInTheDocument();
    expect((screen.getByLabelText("Backend language") as HTMLSelectElement).value).toBe("go");
  });

  it("override : choisir un autre langage appelle onSet", () => {
    const onSet = vi.fn();
    render(<LanguagePanel language="python" complexity={1} criticality={1} onSet={onSet} />);
    fireEvent.change(screen.getByLabelText("Backend language"), { target: { value: "rust" } });
    expect(onSet).toHaveBeenCalledWith("rust");
  });

  it("Node.js explicite reste sélectionné après la pré-analyse", () => {
    render(<LanguagePanel language="node" complexity={2} criticality={1} rationale="Node.js demandé par l'utilisateur." onSet={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "Backend language" })).toHaveValue("node");
    expect(screen.getByRole("option", { name: "Node.js" })).toHaveValue("node");
    expect(screen.getByText("Node.js demandé par l'utilisateur.")).toBeVisible();
  });

  it("sélection Node.js transmet la valeur de contrat node au backend", () => {
    const onSet = vi.fn();
    render(<LanguagePanel language="python" complexity={1} criticality={1} onSet={onSet} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Backend language" }), { target: { value: "node" } });
    expect(onSet).toHaveBeenCalledTimes(1);
    expect(onSet).toHaveBeenCalledWith("node");
  });
});
