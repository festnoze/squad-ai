// Central message registry. Each namespace lives in its own file so that work
// (and parallel edits) on different components never collides. The flat lookup
// table used by `t()` is `messages["<namespace>.<key>"]`.
import { app } from "./app";
import { common } from "./common";
import { settings } from "./settings";
import { projectBar } from "./projectBar";
import { projectSetup } from "./projectSetup";
import { runPanel } from "./runPanel";
import { board } from "./board";
import { activity } from "./activity";
import { llmActivity } from "./llmActivity";
import { chatPanel } from "./chatPanel";
import { componentsPanel } from "./componentsPanel";
import { languagePanel } from "./languagePanel";
import { backlogPanel } from "./backlogPanel";
import { architecturePanel } from "./architecturePanel";
import { planReviewPanel } from "./planReviewPanel";
import { dashboard } from "./dashboard";
import { workspaceViews } from "./workspaceViews";
import { depGraph } from "./depGraph";
import { iterationsView } from "./iterationsView";
import { stepper } from "./stepper";
import { codeViewer } from "./codeViewer";
import { collapsible } from "./collapsible";

export type Entry = { en: string; fr: string };
export type Namespace = Record<string, Entry>;

const namespaces: Record<string, Namespace> = {
  app,
  common,
  settings,
  projectBar,
  projectSetup,
  runPanel,
  board,
  activity,
  llmActivity,
  chatPanel,
  componentsPanel,
  languagePanel,
  backlogPanel,
  architecturePanel,
  planReviewPanel,
  dashboard,
  workspaceViews,
  depGraph,
  iterationsView,
  stepper,
  codeViewer,
  collapsible,
};

export const messages: Record<string, Entry> = {};
for (const [ns, dict] of Object.entries(namespaces)) {
  for (const [key, entry] of Object.entries(dict)) {
    messages[`${ns}.${key}`] = entry;
  }
}
