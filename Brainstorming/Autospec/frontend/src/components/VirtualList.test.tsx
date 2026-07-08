import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VirtualList, windowSlice } from "./VirtualList";

describe("windowSlice (R1)", () => {
  it("fenêtre autour du scroll avec overscan et calcule les cales", () => {
    // 1000 items de 20px, viewport 200px (=10 visibles), scrollTop 4000 (item 200).
    const s = windowSlice(1000, 4000, 200, 20, 6);
    expect(s.start).toBe(200 - 6); // 194
    expect(s.end).toBe(s.start + (10 + 12)); // visibles + 2*overscan
    expect(s.padTop).toBe(s.start * 20);
    expect(s.padBottom).toBe((1000 - s.end) * 20);
  });

  it("borne le début à 0 et la fin au total", () => {
    const s = windowSlice(5, 0, 200, 20, 6);
    expect(s.start).toBe(0);
    expect(s.end).toBe(5);
    expect(s.padTop).toBe(0);
    expect(s.padBottom).toBe(0);
  });
});

describe("VirtualList (R1)", () => {
  it("rend TOUS les items en deçà du seuil (chemin sûr, jsdom)", () => {
    const items = Array.from({ length: 10 }, (_, i) => `row-${i}`);
    render(
      <VirtualList
        items={items}
        itemHeight={20}
        threshold={60}
        testid="vlist"
        renderItem={(it) => <div key={it}>{it}</div>}
      />,
    );
    // Les 10 lignes sont dans le DOM (aucun fenêtrage sous le seuil).
    expect(screen.getByText("row-0")).toBeInTheDocument();
    expect(screen.getByText("row-9")).toBeInTheDocument();
  });

  it("en jsdom (clientHeight 0), rend tout même au-dessus du seuil", () => {
    const items = Array.from({ length: 100 }, (_, i) => `row-${i}`);
    render(
      <VirtualList
        items={items}
        itemHeight={20}
        threshold={60}
        testid="vlist"
        renderItem={(it) => <div key={it}>{it}</div>}
      />,
    );
    // viewport === 0 sous jsdom → chemin « rendu intégral » : row-99 présent.
    expect(screen.getByText("row-99")).toBeInTheDocument();
  });
});
