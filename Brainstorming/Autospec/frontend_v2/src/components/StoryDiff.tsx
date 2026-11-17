import { useEffect, useState } from "react";
import { getStoryDiff, type StoryDiff as StoryDiffData } from "../api";

type Load = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: StoryDiffData };

export function diffLineClass(line: string): string {
  if (line.startsWith("diff ") || line.startsWith("index ")) return "diff-file";
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-meta";
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-del";
  return "diff-ctx";
}

/** Diff of the "<storyId> done" commit, fetched when the story is selected. */
export function StoryDiff({
  projectId,
  storyId,
  onClose,
}: {
  projectId: string;
  storyId: string;
  onClose: () => void;
}) {
  const [load, setLoad] = useState<Load>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setLoad({ status: "loading" });
    getStoryDiff(projectId, storyId).then(
      (data) => {
        if (!cancelled) setLoad({ status: "ready", data });
      },
      (exc: unknown) => {
        if (!cancelled) setLoad({ status: "error", message: exc instanceof Error ? exc.message : String(exc) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [projectId, storyId]);

  return (
    <section className="card diff-panel" aria-labelledby="diff-title">
      <div className="section-head">
        <h2 id="diff-title">Diff de {storyId}</h2>
        <button type="button" onClick={onClose}>
          Fermer le diff
        </button>
      </div>
      {load.status === "loading" && <p className="muted">Chargement du diff...</p>}
      {load.status === "error" && (
        <p className="alert" role="alert">
          {load.message}
        </p>
      )}
      {load.status === "ready" && !load.data.available && (
        <p className="empty">Pas de diff disponible : la story n'a pas encore de commit « {storyId} done ».</p>
      )}
      {load.status === "ready" && load.data.available && (
        <pre className="diff" aria-label={`Diff de ${storyId}`} tabIndex={0}>
          <code>
            {load.data.diff.split("\n").map((line, index) => (
              <span key={index} className={diffLineClass(line)}>
                {line}
              </span>
            ))}
          </code>
        </pre>
      )}
    </section>
  );
}
