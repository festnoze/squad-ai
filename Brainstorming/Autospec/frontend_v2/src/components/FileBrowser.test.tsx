import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockFetch, type MockResponse } from "../test/fetchMock";
import { buildTree, FileBrowser } from "./FileBrowser";

const BASE = "/api/v2/projects/p1";
const FILES = ["todo_cli/app.py", "pyproject.toml", "tests/acceptance/test_us_1.py", "todo_cli/__init__.py"];

describe("buildTree", () => {
  it("nests the paths, folders first, then files, by name", () => {
    const tree = buildTree(FILES);
    expect(tree.map((node) => node.name)).toEqual(["tests", "todo_cli", "pyproject.toml"]);
    expect(tree[0].children?.[0]).toEqual({
      name: "acceptance",
      path: "tests/acceptance",
      children: [{ name: "test_us_1.py", path: "tests/acceptance/test_us_1.py" }],
    });
    expect(tree[1].children?.map((node) => node.path)).toEqual(["todo_cli/__init__.py", "todo_cli/app.py"]);
    expect(tree[2].children).toBeUndefined();
  });
});

describe("FileBrowser", () => {
  it("renders the tree and shows a file read-only", async () => {
    const mock = mockFetch({
      [`GET ${BASE}/files`]: { body: { files: FILES } },
      [`GET ${BASE}/files/raw`]: ({ search }) => ({
        body: { path: search.get("path"), content: "def create_app():\n    ...\n", truncated: false },
      }),
    });
    render(<FileBrowser projectId="p1" />);

    const tree = await screen.findByRole("navigation", { name: "Arborescence du dépôt" });
    expect(await within(tree).findByText("todo_cli/")).toBeTruthy(); // the nav shows "Chargement..." first
    fireEvent.click(within(tree).getByRole("button", { name: "app.py" }));

    const content = await screen.findByLabelText("Contenu de todo_cli/app.py");
    expect(content.tagName).toBe("PRE");
    expect(content.textContent).toBe("def create_app():\n    ...\n");
    expect(screen.queryByRole("textbox")).toBeNull(); // read-only: nothing to edit
    expect(mock.callsTo("GET", `${BASE}/files/raw`)[0].search.get("path")).toBe("todo_cli/app.py");
    expect(within(tree).getByRole("button", { name: "app.py" }).getAttribute("aria-current")).toBe("true");
    expect(screen.queryByText(/Fichier tronqué/)).toBeNull();
  });

  it("warns that a large file is truncated", async () => {
    mockFetch({
      [`GET ${BASE}/files`]: { body: { files: ["big.log"] } },
      [`GET ${BASE}/files/raw`]: { body: { path: "big.log", content: "x", truncated: true } },
    });
    render(<FileBrowser projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "big.log" }));
    expect((await screen.findByRole("status")).textContent).toContain("Fichier tronqué");
  });

  it("reports a file that cannot be read", async () => {
    mockFetch({
      [`GET ${BASE}/files`]: { body: { files: ["gone.py"] } },
      [`GET ${BASE}/files/raw`]: { status: 404, body: { detail: "no such file: gone.py" } },
    });
    render(<FileBrowser projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "gone.py" }));
    expect((await screen.findByRole("alert")).textContent).toBe("gone.py : no such file: gone.py");
  });

  it("shows the last file clicked even when an earlier one answers later", async () => {
    const pending = new Map<string, () => void>();
    mockFetch({
      [`GET ${BASE}/files`]: { body: { files: ["slow.py", "fast.py"] } },
      [`GET ${BASE}/files/raw`]: ({ search }) => {
        const path = search.get("path")!;
        return new Promise<MockResponse>((resolve) => {
          pending.set(path, () => resolve({ body: { path, content: `# ${path}`, truncated: false } }));
        });
      },
    });
    render(<FileBrowser projectId="p1" />);
    fireEvent.click(await screen.findByRole("button", { name: "slow.py" }));
    fireEvent.click(screen.getByRole("button", { name: "fast.py" }));
    await waitFor(() => expect(pending.size).toBe(2));

    await act(async () => pending.get("fast.py")!());
    expect((await screen.findByLabelText("Contenu de fast.py")).textContent).toBe("# fast.py");
    await act(async () => pending.get("slow.py")!());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByLabelText("Contenu de slow.py")).toBeNull();
    expect(screen.getByLabelText("Contenu de fast.py")).toBeTruthy();
    expect(screen.getByRole("button", { name: "fast.py" }).getAttribute("aria-current")).toBe("true");
  });

  it("says when the repository is still empty", async () => {
    mockFetch({ [`GET ${BASE}/files`]: { body: { files: [] } } });
    render(<FileBrowser projectId="p1" />);
    expect(await screen.findByText("Le dépôt est encore vide.")).toBeTruthy();
  });

  it("reloads the list when the refresh key changes", async () => {
    const mock = mockFetch({ [`GET ${BASE}/files`]: { body: { files: ["a.py"] } } });
    const { rerender } = render(<FileBrowser projectId="p1" refreshKey="build:0" />);
    await screen.findByRole("button", { name: "a.py" });
    mock.routes[`GET ${BASE}/files`] = { body: { files: ["a.py", "b.py"] } };
    rerender(<FileBrowser projectId="p1" refreshKey="build:1" />);
    expect(await screen.findByRole("button", { name: "b.py" })).toBeTruthy();
  });
});
