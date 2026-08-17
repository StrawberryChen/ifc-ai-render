export type Project = {
  id: string;
  name: string;
  status: string;
  source_model_url: string;
  staged_model_url: string;
  render_preview_url: string;
  planner_mode: "deepseek" | "local-rules";
};

export type Revision = {
  id: string;
  number: number;
  title: string;
  prompt: string;
  created_at: string;
  preview_url: string;
  status: "ready" | "rendering" | "failed";
  planner?: string;
  actions?: Array<{ tool_id: string; parameters: Record<string, unknown> }>;
  staged_model_url?: string;
  error?: string;
};
