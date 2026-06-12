import {
  FileContent,
  FileListing,
  NewStoryBody,
  ProjectState,
  StoryDiff,
  StoryPatch,
  WsEvent,
} from "./types";

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
  return resp.json();
}

export async function createProject(
  goal: string,
  name: string,
  autoSpec: boolean,
): Promise<{ id: string; state: ProjectState }> {
  return json(
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, name, auto_spec: autoSpec }),
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

export async function deleteProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}`, { method: "DELETE" }));
}

export async function runProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/run`, { method: "POST" }));
}

export async function resumeBuild(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/resume-build`, { method: "POST" }));
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

export function connectEvents(onEvent: (e: WsEvent) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;

  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage = (msg) => onEvent(JSON.parse(msg.data));
    ws.onclose = () => {
      if (!closed) setTimeout(open, 1500);
    };
  };
  open();

  return () => {
    closed = true;
    ws?.close();
  };
}
