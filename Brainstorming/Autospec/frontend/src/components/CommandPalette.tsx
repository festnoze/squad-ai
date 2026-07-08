import { useEffect, useMemo, useRef, useState } from "react";
import { forceDoneStory, forceDoneTask, rebuildStory, rebuildTask } from "../api";
import { dispatchNav } from "../navigation";
import { effectiveStatus } from "../work";
import { UserStory } from "../types";
import { useEscapeToClose } from "../hooks";
import { useI18n } from "../i18n/i18n";
import { confirmAction } from "./ConfirmDialog";
import { notify } from "../toast";

/** One targetable work item (a story or one of its tasks). */
export interface PaletteItem {
  id: string;
  title: string;
  kind: "story" | "task";
  status: string;
}

/** Flatten a project's stories + tasks into targetable palette items. */
export function paletteItems(stories: UserStory[]): PaletteItem[] {
  const out: PaletteItem[] = [];
  for (const s of stories) {
    out.push({ id: s.id, title: s.title, kind: "story", status: effectiveStatus(s) });
    for (const task of s.tasks ?? []) {
      out.push({ id: task.id, title: task.title, kind: "task", status: task.status });
    }
  }
  return out;
}

/** Diacritic-insensitive substring match with a light ranking (earlier = better;
 * a prefix/id match beats a mid-string one). Returns -1 when there is no match. */
export function fuzzyScore(haystack: string, needle: string): number {
  if (needle === "") return 0;
  const h = haystack.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const n = needle.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const i = h.indexOf(n);
  return i === -1 ? -1 : i;
}

interface Command {
  id: string;
  label: string;
  hint: string;
  danger?: boolean;
  needsTarget?: boolean;
  run?: () => void | Promise<void>;
  runOnTarget?: (item: PaletteItem) => void | Promise<void>;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** Current project's items (empty when no project is selected). */
  items: PaletteItem[];
  projectId: string | null;
  hasProject: boolean;
  hasGraph: boolean;
  multiIter: boolean;
  onNewProject: () => void;
  onOpenDashboard: () => void;
  onOpenSettings: () => void;
}

/**
 * R2 — global command palette (Cmd/Ctrl-K). Two modes:
 *  - root: global commands (view switches, dashboard/settings/new) + item verbs;
 *  - target: after picking a verb that needs a target, a mandatory target chip is
 *    shown and the list filters work items. Destructive verbs route through
 *    `confirmAction`; navigation goes through the `dispatchNav` bus.
 */
export function CommandPalette({
  open,
  onClose,
  items,
  projectId,
  hasProject,
  hasGraph,
  multiIter,
  onNewProject,
  onOpenDashboard,
  onOpenSettings,
}: Props) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0);
  const [verb, setVerb] = useState<Command | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset transient state every time the palette opens.
  useEffect(() => {
    if (open) {
      setQuery("");
      setSel(0);
      setVerb(null);
      inputRef.current?.focus();
    }
  }, [open]);

  const close = () => {
    onClose();
  };
  useEscapeToClose(open, () => {
    // Target mode → back to root; root → close.
    if (verb) {
      setVerb(null);
      setQuery("");
      setSel(0);
    } else {
      close();
    }
  });

  const gotoItem = (storyId: string) => {
    dispatchNav({ type: "view", view: "vision" });
    dispatchNav({ type: "goto-item", storyId });
    close();
  };

  const commands = useMemo<Command[]>(() => {
    const cmds: Command[] = [];
    if (hasProject) {
      cmds.push(
        {
          id: "view-activity",
          label: t("palette.goActivity"),
          hint: t("palette.hintView"),
          run: () => {
            dispatchNav({ type: "view", view: "activity" });
            close();
          },
        },
        {
          id: "view-vision",
          label: t("palette.goVision"),
          hint: t("palette.hintView"),
          run: () => {
            dispatchNav({ type: "view", view: "vision" });
            close();
          },
        },
      );
      if (hasGraph)
        cmds.push({
          id: "view-graph",
          label: t("palette.goGraph"),
          hint: t("palette.hintView"),
          run: () => {
            dispatchNav({ type: "view", view: "graph" });
            close();
          },
        });
      if (multiIter)
        cmds.push({
          id: "view-iterations",
          label: t("palette.goIterations"),
          hint: t("palette.hintView"),
          run: () => {
            dispatchNav({ type: "view", view: "iterations" });
            close();
          },
        });
      // "Go to next failure": jump to the first failed item on the board.
      const firstFailure = items.find((it) => it.status === "failed");
      if (firstFailure)
        cmds.push({
          id: "goto-next-failure",
          label: t("palette.nextFailure"),
          hint: t("palette.hintNav"),
          run: () => gotoItem(firstFailure.id),
        });
      cmds.push(
        { id: "goto", label: t("palette.goToItem"), hint: t("palette.hintNav"), needsTarget: true },
        { id: "retry", label: t("palette.retryItem"), hint: t("palette.hintAction"), needsTarget: true },
        {
          id: "force",
          label: t("palette.forceItem"),
          hint: t("palette.hintAction"),
          danger: true,
          needsTarget: true,
        },
      );
    }
    cmds.push(
      { id: "new-project", label: t("palette.newProject"), hint: t("palette.hintApp"), run: () => { onNewProject(); close(); } },
      { id: "open-dashboard", label: t("palette.openDashboard"), hint: t("palette.hintApp"), run: () => { onOpenDashboard(); close(); } },
      { id: "open-settings", label: t("palette.openSettings"), hint: t("palette.hintApp"), run: () => { onOpenSettings(); close(); } },
    );
    return cmds;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasProject, hasGraph, multiIter, items, t]);

  const runOnTarget = async (item: PaletteItem) => {
    if (!verb || !projectId) return;
    if (verb.id === "goto") {
      // Task or story: navigate to the owning story (tasks live under a story).
      gotoItem(item.id);
      return;
    }
    if (verb.id === "force") {
      const ok = await confirmAction({
        title: t("palette.confirmForceTitle"),
        body: t("palette.confirmForceBody", { id: item.id }),
        danger: true,
      });
      if (!ok) return;
    }
    close();
    try {
      if (verb.id === "retry") {
        await (item.kind === "task" ? rebuildTask(projectId, item.id) : rebuildStory(projectId, item.id));
      } else if (verb.id === "force") {
        await (item.kind === "task" ? forceDoneTask(projectId, item.id) : forceDoneStory(projectId, item.id));
      }
    } catch (e) {
      notify("error", t("palette.actionFailed"), e instanceof Error ? e.message : String(e));
    }
  };

  // The visible list depends on the mode.
  const rootResults = useMemo(
    () =>
      commands
        .map((c) => ({ c, score: fuzzyScore(c.label, query) }))
        .filter((r) => r.score >= 0)
        .sort((a, b) => a.score - b.score)
        .map((r) => r.c),
    [commands, query],
  );
  const targetResults = useMemo(
    () =>
      items
        .map((it) => ({ it, score: Math.min(...[fuzzyScore(it.id, query), fuzzyScore(it.title, query)].map((s) => (s < 0 ? Infinity : s))) }))
        .filter((r) => r.score !== Infinity)
        .sort((a, b) => a.score - b.score)
        .slice(0, 50)
        .map((r) => r.it),
    [items, query],
  );

  const listLen = verb ? targetResults.length : rootResults.length;

  // Keep the selection index in range as the filtered list changes.
  useEffect(() => {
    setSel((s) => (listLen === 0 ? 0 : Math.min(s, listLen - 1)));
  }, [listLen]);

  if (!open) return null;

  const pickRoot = (c: Command) => {
    if (c.needsTarget) {
      setVerb(c);
      setQuery("");
      setSel(0);
      inputRef.current?.focus();
    } else {
      void c.run?.();
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => (listLen === 0 ? 0 : (s + 1) % listLen));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => (listLen === 0 ? 0 : (s - 1 + listLen) % listLen));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (verb) {
        const it = targetResults[sel];
        if (it) void runOnTarget(it);
      } else {
        const c = rootResults[sel];
        if (c) pickRoot(c);
      }
    } else if (e.key === "Backspace" && query === "" && verb) {
      e.preventDefault();
      setVerb(null);
      setSel(0);
    }
  };

  return (
    <div className="palette-backdrop" data-testid="command-palette" onClick={close}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label={t("palette.title")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="palette-input-row">
          {verb && (
            <span className="palette-chip" data-testid="palette-verb-chip">
              {verb.label}
            </span>
          )}
          <input
            ref={inputRef}
            className="palette-input"
            type="text"
            value={query}
            aria-label={t("palette.inputAria")}
            placeholder={verb ? t("palette.targetPlaceholder") : t("palette.rootPlaceholder")}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
          />
        </div>
        <ul className="palette-list" role="listbox" data-testid="palette-list">
          {listLen === 0 && <li className="palette-empty">{t("palette.noResult")}</li>}
          {!verb &&
            rootResults.map((c, i) => (
              <li
                key={c.id}
                role="option"
                aria-selected={i === sel}
                className={`palette-row${i === sel ? " active" : ""}${c.danger ? " danger" : ""}`}
                data-testid={`palette-cmd-${c.id}`}
                onMouseEnter={() => setSel(i)}
                onClick={() => pickRoot(c)}
              >
                <span className="palette-row-label">{c.label}</span>
                <span className="palette-row-hint">{c.hint}</span>
              </li>
            ))}
          {verb &&
            targetResults.map((it, i) => (
              <li
                key={`${it.kind}-${it.id}`}
                role="option"
                aria-selected={i === sel}
                className={`palette-row${i === sel ? " active" : ""}`}
                data-testid={`palette-target-${it.id}`}
                onMouseEnter={() => setSel(i)}
                onClick={() => void runOnTarget(it)}
              >
                <span className="palette-row-id">{it.id}</span>
                <span className="palette-row-label">{it.title}</span>
                <span className={`palette-row-status status-${it.status}`}>{it.status}</span>
              </li>
            ))}
        </ul>
      </div>
    </div>
  );
}
