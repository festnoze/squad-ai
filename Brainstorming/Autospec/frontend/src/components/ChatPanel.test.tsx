import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";

// jsdom has no layout engine — ChatPanel auto-scrolls to its bottom anchor.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const baseProps = {
  chat: [],
  phase: "spec" as const,
  onSend: vi.fn(),
  specMode: "interview" as const,
  onSetSpecMode: vi.fn(),
};

describe("ChatPanel — brainstorming offer (B-IDEA)", () => {
  it("n'affiche pas l'offre de brainstorming par défaut", () => {
    render(<ChatPanel {...baseProps} />);
    expect(screen.queryByText(/on explore ensemble/)).not.toBeInTheDocument();
  });

  it("affiche l'offre + les techniques quand une idée vague est détectée", () => {
    render(
      <ChatPanel
        {...baseProps}
        awaitingBrainstorm
        brainstormTechniques={["What If Scenarios", "Five Whys"]}
        onResolveBrainstorm={vi.fn()}
      />,
    );
    expect(screen.getByText(/idée est encore ouverte/i)).toBeInTheDocument();
    expect(screen.getByText(/What If Scenarios, Five Whys/)).toBeInTheDocument();
  });

  it("« Oui » résout l'offre avec accept=true", () => {
    const onResolveBrainstorm = vi.fn();
    render(
      <ChatPanel {...baseProps} awaitingBrainstorm onResolveBrainstorm={onResolveBrainstorm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Oui, on explore ensemble/ }));
    expect(onResolveBrainstorm).toHaveBeenCalledWith(true);
  });

  it("« Non » résout l'offre avec accept=false (mode autonome)", () => {
    const onResolveBrainstorm = vi.fn();
    render(
      <ChatPanel {...baseProps} awaitingBrainstorm onResolveBrainstorm={onResolveBrainstorm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Non, affine en autonomie/ }));
    expect(onResolveBrainstorm).toHaveBeenCalledWith(false);
  });
});
