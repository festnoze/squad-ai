import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MobileNav } from "./MobileNav";

describe("MobileNav (R5)", () => {
  it("reflète le volet actif via aria-selected", () => {
    render(<MobileNav pane="scene" onChange={vi.fn()} />);
    expect(screen.getByTestId("mobile-nav-scene")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("mobile-nav-rail")).toHaveAttribute("aria-selected", "false");
  });

  it("un clic sur un onglet notifie le changement de volet", () => {
    const onChange = vi.fn();
    render(<MobileNav pane="rail" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("mobile-nav-scene"));
    expect(onChange).toHaveBeenCalledWith("scene");
  });
});
