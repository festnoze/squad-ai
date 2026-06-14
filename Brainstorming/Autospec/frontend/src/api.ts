import {
  FileContent,
  FileListing,
  NewStoryBody,
  ProductComponent,
  ProjectState,
  ProviderInfo,
  StoryDiff,
  StoryPatch,
  Metrics,
  WsEvent,
} from "./types";

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text();
    // FastAPI renvoie {"detail": "..."} : on extrait le message lisible.
    let detail = body;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // Corps non-JSON : on garde le texte brut.
    }
    throw new Error(`Erreur ${resp.status} : ${detail}`);
  }
  return resp.json();
}

/** Message lisible d'une erreur inconnue (évite « Error: Error: … »). */
export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export async function createProject(
  goal: string,
  name: string,
  autoSpec: boolean,
  budgetUsd?: number,
  brief?: string,
  brownfieldPath?: string,
): Promise<{ id: string; state: ProjectState }> {
  const body: {
    goal: string;
    name: string;
    auto_spec: boolean;
    budget_usd?: number;
    brief?: string;
    brownfield_path?: string;
  } = { goal, name, auto_spec: autoSpec };
  if (budgetUsd != null && budgetUsd > 0) body.budget_usd = budgetUsd;
  if (brief && brief.trim()) body.brief = brief;
  if (brownfieldPath && brownfieldPath.trim()) body.brownfield_path = brownfieldPath;
  return json(
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function listProjects(): Promise<ProjectState[]> {
  return json(await fetch("/api/projects"));
}

export async function sendChat(projectId: string, message: string): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  );
}

export async function setSpecMode(
  projectId: string,
  mode: "interview" | "brainstorm",
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/spec-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
  );
}

export async function stopProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/stop`, { method: "POST" }));
}

export async function stopApp(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/stop-app`, { method: "POST" }));
}

export async function pauseProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/pause`, { method: "POST" }));
}

export async function resumeProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/resume`, { method: "POST" }));
}

export async function approveProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/approve`, { method: "POST" }));
}

export async function rejectProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/reject`, { method: "POST" }));
}

export async function getIterations(projectId: string): Promise<number[]> {
  const r = await json(await fetch(`/api/projects/${projectId}/iterations`));
  return (r as { iterations: number[] }).iterations;
}

export async function rollbackProject(projectId: string, iteration: number): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/rollback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ iteration }),
    }),
  );
}

export async function deployProject(projectId: string): Promise<{ created: string[] }> {
  return json(
    await fetch(`/api/projects/${projectId}/deploy`, { method: "POST" }),
  ) as Promise<{ created: string[] }>;
}

export async function deleteProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}`, { method: "DELETE" }));
}

export async function archiveProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/archive`, { method: "POST" }));
}

export async function unarchiveProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/unarchive`, { method: "POST" }));
}

export async function runProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/run`, { method: "POST" }));
}

export async function resumeBuild(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/resume-build`, { method: "POST" }));
}

export async function cancelResume(projectId: string): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/cancel-resume`, { method: "POST" }),
  );
}

export async function editStory(
  projectId: string,
  storyId: string,
  patch: StoryPatch,
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/stories/${storyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  );
}

export async function addStory(
  projectId: string,
  body: NewStoryBody,
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/stories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteStory(projectId: string, storyId: string): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/stories/${storyId}`, { method: "DELETE" }),
  );
}

export async function rebuildStory(
  projectId: string,
  storyId: string,
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/stories/${storyId}/rebuild`, {
      method: "POST",
    }),
  );
}

export async function forceDoneStory(
  projectId: string,
  storyId: string,
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/stories/${storyId}/force-done`, {
      method: "POST",
    }),
  );
}

export async function reorderStories(
  projectId: string,
  priorities: { id: string; priority: number }[],
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/stories/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ priorities }),
    }),
  );
}

export async function listFiles(projectId: string): Promise<FileListing> {
  return json(await fetch(`/api/projects/${projectId}/files`));
}

export async function readFile(
  projectId: string,
  path: string,
): Promise<FileContent> {
  return json(
    await fetch(
      `/api/projects/${projectId}/files/raw?path=${encodeURIComponent(path)}`,
    ),
  );
}

export async function storyDiff(
  projectId: string,
  storyId: string,
): Promise<{ available: boolean; diff: string }> {
  const res = await json<StoryDiff>(
    await fetch(`/api/projects/${projectId}/stories/${storyId}/diff`),
  );
  return { available: res.available, diff: res.diff };
}

export async function getProvider(): Promise<ProviderInfo> {
  return json(await fetch("/api/provider"));
}

export async function setProvider(
  provider: string,
  model?: string,
): Promise<ProviderInfo> {
  return json(
    await fetch("/api/provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(model ? { provider, model } : { provider }),
    }),
  );
}

export async function updateComponents(
  projectId: string,
  components: ProductComponent[],
): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/components`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ components }),
    }),
  );
}

export async function setupComponents(projectId: string): Promise<void> {
  await json(
    await fetch(`/api/projects/${projectId}/components/setup`, { method: "POST" }),
  );
}

export async function documentProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/document`, { method: "POST" }));
}

export async function gitExportProject(
  projectId: string,
): Promise<{ commit: string }> {
  return json(
    await fetch(`/api/projects/${projectId}/git-export`, { method: "POST" }),
  );
}

/** URL de téléchargement du zip du workspace généré (lien direct). */
export function exportZipUrl(projectId: string): string {
  return `/api/projects/${projectId}/export`;
}

export function connectEvents(
  onEvent: (e: WsEvent) => void,
  onReconnect?: () => void,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let opened = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      // La toute première ouverture est gérée par l'init initial du composant ;
      // on ne resynchronise qu'à chaque RE-connexion suivante.
      if (opened) onReconnect?.();
      opened = true;
    };
    ws.onmessage = (msg) => {
      let event: WsEvent;
      try {
        event = JSON.parse(msg.data) as WsEvent;
      } catch {
        // Frame illisible : on l'ignore pour ne pas casser le flux d'événements.
        console.warn("Frame WebSocket illisible ignorée");
        return;
      }
      onEvent(event);
    };
    ws.onclose = () => {
      if (!closed) reconnectTimer = setTimeout(open, 1500);
    };
  };
  open();

  return () => {
    closed = true;
    // Annule une reconnexion en attente : sans cela, un timer déjà programmé
    // rouvrirait une WebSocket orpheline après le démontage du composant.
    if (reconnectTimer !== undefined) clearTimeout(reconnectTimer);
    ws?.close();
  };
}

export async function getMetrics(): Promise<Metrics> {
  return json(await fetch("/api/metrics")) as Promise<Metrics>;
}
