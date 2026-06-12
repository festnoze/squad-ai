import { ProjectState, WsEvent } from "./types";

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

export async function deleteProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}`, { method: "DELETE" }));
}

export async function runProject(projectId: string): Promise<void> {
  await json(await fetch(`/api/projects/${projectId}/run`, { method: "POST" }));
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
