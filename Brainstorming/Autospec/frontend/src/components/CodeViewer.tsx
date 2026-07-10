import { useEffect, useMemo, useState } from "react";
import { listFiles, readFile, revealFile } from "../api";
import { copyText } from "../clipboard";
import { FileContent } from "../types";
import { useEscapeToClose } from "../hooks";
import { useI18n } from "../i18n/i18n";
import { notify } from "../toast";

interface Props {
  projectId: string;
}

/** A node in the workspace file tree, built from the flat path listing. */
interface TreeNode {
  name: string;
  /** POSIX path relative to the workspace root. */
  path: string;
  isDir: boolean;
  children: TreeNode[];
}

/** Currently highlighted tree entry (file or directory). */
interface Selection {
  path: string;
  isDir: boolean;
}

/** Fold a sorted list of relative file paths into a nested directory tree. */
function buildTree(files: string[]): TreeNode[] {
  const roots: TreeNode[] = [];
  const byPath = new Map<string, TreeNode>();
  for (const file of files) {
    const parts = file.split("/");
    let prefix = "";
    let siblings = roots;
    parts.forEach((name, i) => {
      prefix = prefix ? `${prefix}/${name}` : name;
      const isDir = i < parts.length - 1;
      let node = byPath.get(prefix);
      if (!node) {
        node = { name, path: prefix, isDir, children: [] };
        byPath.set(prefix, node);
        siblings.push(node);
      }
      siblings = node.children;
    });
  }
  // Directories first, then files, each group alphabetical.
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) =>
      a.isDir === b.isDir
        ? a.name.localeCompare(b.name)
        : a.isDir
          ? -1
          : 1,
    );
    nodes.forEach((n) => sort(n.children));
  };
  sort(roots);
  return roots;
}

/** Every directory path in the tree — used to expand the tree by default. */
function allDirPaths(nodes: TreeNode[]): string[] {
  const dirs: string[] = [];
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      if (n.isDir) {
        dirs.push(n.path);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return dirs;
}

interface TreeProps {
  nodes: TreeNode[];
  depth: number;
  selected: Selection | null;
  expanded: Set<string>;
  onSelect: (sel: Selection) => void;
  onToggle: (path: string) => void;
}

function Tree({ nodes, depth, selected, expanded, onSelect, onToggle }: TreeProps) {
  return (
    <>
      {nodes.map((node) => {
        const isSelected = selected?.path === node.path;
        const isOpen = expanded.has(node.path);
        return (
          <div key={node.path}>
            <button
              type="button"
              className={"code-viewer-node" + (isSelected ? " active" : "")}
              style={{ paddingLeft: 6 + depth * 14 }}
              title={node.path}
              onClick={() => {
                onSelect({ path: node.path, isDir: node.isDir });
                if (node.isDir) onToggle(node.path);
              }}
            >
              <span className="code-viewer-node-icon">
                {node.isDir ? (isOpen ? "📂" : "📁") : "📄"}
              </span>
              <span className="code-viewer-node-name">{node.name}</span>
            </button>
            {node.isDir && isOpen && node.children.length > 0 && (
              <Tree
                nodes={node.children}
                depth={depth + 1}
                selected={selected}
                expanded={expanded}
                onSelect={onSelect}
                onToggle={onToggle}
              />
            )}
          </div>
        );
      })}
    </>
  );
}

export function CodeViewer({ projectId }: Props) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [file, setFile] = useState<FileContent | null>(null);
  const [listError, setListError] = useState("");
  const [fileError, setFileError] = useState("");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  useEscapeToClose(open, () => setOpen(false));

  const tree = useMemo(() => buildTree(files), [files]);

  // Charge la liste des fichiers à l'ouverture.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingList(true);
    setListError("");
    setFiles([]);
    setSelected(null);
    setExpanded(new Set());
    setFile(null);
    listFiles(projectId)
      .then((res) => {
        if (cancelled) return;
        setFiles(res.files);
        setExpanded(new Set(allDirPaths(buildTree(res.files))));
        if (res.files.length > 0)
          setSelected({ path: res.files[0], isDir: false });
      })
      .catch((e) => {
        if (!cancelled) setListError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId]);

  // Charge le contenu du fichier sélectionné (les dossiers n'ont pas de contenu).
  useEffect(() => {
    if (!open || !selected || selected.isDir) {
      setFile(null);
      setFileError("");
      return;
    }
    let cancelled = false;
    setLoadingFile(true);
    setFileError("");
    readFile(projectId, selected.path)
      .then((res) => {
        if (!cancelled) setFile(res);
      })
      .catch((e) => {
        if (!cancelled) {
          setFile(null);
          setFileError(String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingFile(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, selected, projectId]);

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const reveal = () => {
    revealFile(projectId, selected?.path ?? "")
      .then((res) => {
        if (res.revealed) {
          notify("success", t("codeViewer.revealed"), res.path);
        } else {
          void copyText(res.path);
          notify("info", t("codeViewer.pathCopied"), res.path);
        }
      })
      .catch((e) => notify("error", String(e)));
  };

  const copyPath = () => {
    revealFile(projectId, selected?.path ?? "")
      .then((res) => {
        void copyText(res.path);
        notify("success", t("codeViewer.pathCopied"), res.path);
      })
      .catch((e) => notify("error", String(e)));
  };

  return (
    <>
      <button
        type="button"
        className="ghost code-viewer-btn"
        onClick={() => setOpen(true)}
      >
        📁 {t("codeViewer.generatedCode")}
      </button>
      {open && (
        <div
          className="code-viewer-overlay"
          onClick={() => setOpen(false)}
        >
          <div
            className="code-viewer-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="code-viewer-header">
              <span className="code-viewer-title">📁 {t("codeViewer.generatedCode")}</span>
              <button
                type="button"
                className="ghost small-btn"
                disabled={loadingFile || !file}
                onClick={() => file && void copyText(file.content)}
                title={t("common.copy")}
              >
                📋 {t("common.copy")}
              </button>
              <button
                type="button"
                className="ghost code-viewer-close"
                onClick={() => setOpen(false)}
                aria-label={t("common.close")}
              >
                ✕
              </button>
            </div>
            <div className="code-viewer-body">
              <div className="code-viewer-side">
                <div className="code-viewer-files">
                  {loadingList && (
                    <div className="code-viewer-muted">{t("common.loading")}</div>
                  )}
                  {listError && (
                    <div className="code-viewer-error">{listError}</div>
                  )}
                  {!loadingList && !listError && files.length === 0 && (
                    <div className="code-viewer-muted">{t("codeViewer.noFiles")}</div>
                  )}
                  {!loadingList && !listError && files.length > 0 && (
                    <Tree
                      nodes={tree}
                      depth={0}
                      selected={selected}
                      expanded={expanded}
                      onSelect={setSelected}
                      onToggle={toggle}
                    />
                  )}
                </div>
                <div className="code-viewer-toolbar">
                  <button
                    type="button"
                    className="ghost small-btn"
                    disabled={loadingList || !!listError || files.length === 0}
                    onClick={reveal}
                    title={t("codeViewer.revealHint")}
                  >
                    🗂️ {t("codeViewer.reveal")}
                  </button>
                  <button
                    type="button"
                    className="ghost small-btn"
                    disabled={loadingList || !!listError || files.length === 0}
                    onClick={copyPath}
                    title={t("codeViewer.copyPathHint")}
                  >
                    🔗 {t("codeViewer.copyPath")}
                  </button>
                </div>
              </div>
              <div className="code-viewer-content">
                {selected?.isDir && (
                  <div className="code-viewer-muted">
                    {t("codeViewer.selectFile")}
                  </div>
                )}
                {!selected?.isDir && loadingFile && (
                  <div className="code-viewer-muted">{t("common.loading")}</div>
                )}
                {!selected?.isDir && fileError && (
                  <div className="code-viewer-error">{fileError}</div>
                )}
                {!selected?.isDir && !loadingFile && !fileError && file && (
                  <>
                    {file.truncated && (
                      <div className="code-viewer-truncated">
                        {t("codeViewer.truncated")}
                      </div>
                    )}
                    <pre className="code-viewer-pre">{file.content}</pre>
                  </>
                )}
                {!loadingFile && !fileError && !file && !selected && (
                  <div className="code-viewer-muted">
                    {t("codeViewer.selectFile")}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
