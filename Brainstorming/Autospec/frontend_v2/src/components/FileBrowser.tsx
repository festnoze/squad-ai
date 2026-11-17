import { useCallback, useEffect, useRef, useState } from "react";
import { listFiles, readFile, type FileContent } from "../api";

export interface TreeNode {
  name: string;
  path: string;
  children?: TreeNode[]; // present on folders only
}

/** Turns POSIX paths into a tree: folders first, then files, each sorted by name. */
export function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", children: [] };
  for (const path of paths) {
    const parts = path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      const siblings = node.children!;
      let child = siblings.find((candidate) => candidate.name === part && !candidate.children === isFile);
      if (!child) {
        child = { name: part, path: parts.slice(0, index + 1).join("/") };
        if (!isFile) child.children = [];
        siblings.push(child);
      }
      node = child;
    });
  }
  const sort = (nodes: TreeNode[]): TreeNode[] =>
    nodes
      .sort((a, b) => Number(!a.children) - Number(!b.children) || a.name.localeCompare(b.name))
      .map((node) => (node.children ? { ...node, children: sort(node.children) } : node));
  return sort(root.children!);
}

type Viewer =
  | { status: "idle" }
  | { status: "loading"; path: string }
  | { status: "error"; path: string; message: string }
  | { status: "ready"; file: FileContent };

export function FileBrowser({ projectId, refreshKey }: { projectId: string; refreshKey?: string }) {
  const [files, setFiles] = useState<string[] | null>(null);
  const [listError, setListError] = useState("");
  const [viewer, setViewer] = useState<Viewer>({ status: "idle" });

  const loadList = useCallback(async () => {
    try {
      setFiles((await listFiles(projectId)).files);
      setListError("");
    } catch (exc) {
      setListError(exc instanceof Error ? exc.message : String(exc));
    }
  }, [projectId]);

  useEffect(() => {
    void loadList();
  }, [loadList, refreshKey]);

  // Only the last file clicked may fill the viewer: an older, slower response is dropped.
  const lastRequest = useRef(0);

  async function open(path: string) {
    const request = ++lastRequest.current;
    setViewer({ status: "loading", path });
    let next: Viewer;
    try {
      next = { status: "ready", file: await readFile(projectId, path) };
    } catch (exc) {
      next = { status: "error", path, message: exc instanceof Error ? exc.message : String(exc) };
    }
    if (request === lastRequest.current) setViewer(next);
  }

  const selected = viewer.status === "ready" ? viewer.file.path : viewer.status === "idle" ? null : viewer.path;

  return (
    <section className="card" aria-labelledby="files-title">
      <div className="section-head">
        <h2 id="files-title">Fichiers</h2>
        <button type="button" onClick={() => void loadList()}>
          Actualiser les fichiers
        </button>
      </div>
      {listError && (
        <p className="alert" role="alert">
          {listError}
        </p>
      )}
      <div className="files">
        <nav className="file-tree" aria-label="Arborescence du dépôt">
          {files === null && !listError && <p className="muted">Chargement...</p>}
          {files !== null && files.length === 0 && <p className="empty">Le dépôt est encore vide.</p>}
          {files !== null && files.length > 0 && <TreeList nodes={buildTree(files)} selected={selected} onOpen={open} />}
        </nav>
        <div className="file-viewer">
          {viewer.status === "idle" && <p className="muted">Choisissez un fichier pour l'afficher (lecture seule).</p>}
          {viewer.status === "loading" && <p className="muted">Chargement de {viewer.path}...</p>}
          {viewer.status === "error" && (
            <p className="alert" role="alert">
              {viewer.path} : {viewer.message}
            </p>
          )}
          {viewer.status === "ready" && (
            <>
              <h3 className="mono file-path">{viewer.file.path}</h3>
              {viewer.file.truncated && (
                <p className="notice" role="status">
                  Fichier tronqué : seul le début est affiché.
                </p>
              )}
              <pre className="file-content" aria-label={`Contenu de ${viewer.file.path}`} tabIndex={0}>
                <code>{viewer.file.content}</code>
              </pre>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function TreeList({
  nodes,
  selected,
  onOpen,
}: {
  nodes: TreeNode[];
  selected: string | null;
  onOpen: (path: string) => void;
}) {
  return (
    <ul className="tree">
      {nodes.map((node) =>
        node.children ? (
          <li key={node.path}>
            <details open={selected?.startsWith(`${node.path}/`) || undefined}>
              <summary>{node.name}/</summary>
              <TreeList nodes={node.children} selected={selected} onOpen={onOpen} />
            </details>
          </li>
        ) : (
          <li key={node.path}>
            <button
              type="button"
              className="file"
              title={node.path}
              aria-current={selected === node.path ? "true" : undefined}
              onClick={() => onOpen(node.path)}
            >
              {node.name}
            </button>
          </li>
        ),
      )}
    </ul>
  );
}
