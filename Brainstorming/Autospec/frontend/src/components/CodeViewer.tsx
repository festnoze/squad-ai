import { useEffect, useState } from "react";
import { listFiles, readFile } from "../api";
import { FileContent } from "../types";
import { useI18n } from "../i18n/i18n";

interface Props {
  projectId: string;
}

export function CodeViewer({ projectId }: Props) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [file, setFile] = useState<FileContent | null>(null);
  const [listError, setListError] = useState("");
  const [fileError, setFileError] = useState("");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);

  // Charge la liste des fichiers à l'ouverture.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingList(true);
    setListError("");
    setFiles([]);
    setSelected(null);
    setFile(null);
    listFiles(projectId)
      .then((res) => {
        if (cancelled) return;
        setFiles(res.files);
        if (res.files.length > 0) setSelected(res.files[0]);
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

  // Charge le contenu du fichier sélectionné.
  useEffect(() => {
    if (!open || !selected) {
      setFile(null);
      return;
    }
    let cancelled = false;
    setLoadingFile(true);
    setFileError("");
    readFile(projectId, selected)
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
                className="ghost code-viewer-close"
                onClick={() => setOpen(false)}
                aria-label={t("common.close")}
              >
                ✕
              </button>
            </div>
            <div className="code-viewer-body">
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
                {files.map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={
                      "code-viewer-file" + (f === selected ? " active" : "")
                    }
                    onClick={() => setSelected(f)}
                    title={f}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <div className="code-viewer-content">
                {loadingFile && (
                  <div className="code-viewer-muted">{t("common.loading")}</div>
                )}
                {fileError && (
                  <div className="code-viewer-error">{fileError}</div>
                )}
                {!loadingFile && !fileError && file && (
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
