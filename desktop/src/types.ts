export type Project = {
  id: string;
  name: string;
  status: string;
  source_model_url: string;
  source_texture_url: string;
  staged_model_url: string;
  render_preview_url: string;
};

export type Revision = {
  id: string;
  number: number;
  title: string;
  prompt: string;
  created_at: string;
  preview_url: string;
};
