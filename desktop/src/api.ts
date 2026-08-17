import type { Project, Revision } from "./types";

export const API = "http://127.0.0.1:8765";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export const getProject = () => request<Project>("/api/projects/current");
export const getRevisions = () => request<Revision[]>("/api/revisions?limit=5");
export const submitPrompt = (prompt: string) => request<{ revision: Revision; message: string }>(
  "/api/prompts/preview",
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) },
);
export const restoreRevision = (id: string) => request<Revision>(`/api/revisions/${id}/restore`, { method: "POST" });
