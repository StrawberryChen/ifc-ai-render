import { useEffect, useState } from "react";
import { Box, ChevronRight, Clock3, History, Image, LoaderCircle, RotateCcw, Send, Sparkles } from "lucide-react";
import ModelViewer from "./ModelViewer";
import { API, getProject, getRevisions, restoreRevision, submitPrompt } from "./api";
import type { Project, Revision } from "./types";

const examples = [
  "改为初秋黄昏，天空偏蓝紫色，开启暖色建筑亮窗",
  "降低主入口前乔木密度，保持教学楼和道路不变",
  "将鸟瞰相机焦距调整为 50mm，完整展示运动场",
];

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [tab, setTab] = useState<"source" | "staged" | "render">("source");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = async () => {
    const [nextProject, nextRevisions] = await Promise.all([getProject(), getRevisions()]);
    setProject(nextProject); setRevisions(nextRevisions);
  };
  useEffect(() => { refresh().catch(() => setMessage("本地服务尚未启动，请检查 FastAPI。")); }, []);

  const submit = async () => {
    if (prompt.trim().length < 2) return;
    setBusy(true); setMessage("");
    try { const result = await submitPrompt(prompt); setMessage(result.message); setPrompt(""); await refresh(); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  };

  const restore = async (id: string) => {
    setBusy(true);
    try { await restoreRevision(id); await refresh(); setMessage(`已从 ${id} 创建新的恢复版本。`); }
    finally { setBusy(false); }
  };

  return <main>
    <header>
      <div className="brand"><span className="brand-mark"><Box size={19} /></span><div><strong>FormRender</strong><small>建筑可视化工作台</small></div></div>
      <div className="project-title"><span className="status-dot" />{project?.name ?? "正在连接项目…"}</div>
      <button className="render-button"><Sparkles size={16} />生成快速预览</button>
    </header>

    <section className="workspace">
      <div className="stage-panel">
        <nav className="view-tabs">
          <button className={tab === "source" ? "active" : ""} onClick={() => setTab("source")}><Box size={15} />原始模型</button>
          <button className={tab === "staged" ? "active" : ""} onClick={() => setTab("staged")}><Sparkles size={15} />布景模型</button>
          <button className={tab === "render" ? "active" : ""} onClick={() => setTab("render")}><Image size={15} />渲染预览</button>
        </nav>
        <div className="viewport">
          {project && tab !== "render" && <ModelViewer modelUrl={`${API}${tab === "source" ? project.source_model_url : project.staged_model_url}`} textureUrl={`${API}${project.source_texture_url}`} staged={tab === "staged"} />}
          {project && tab === "render" && <img className="render-preview" src={`${API}${project.render_preview_url}`} alt="Blender render preview" />}
          {!project && <div className="loading"><LoaderCircle className="spin" />连接本地项目…</div>}
          <div className="viewport-hint">拖动旋转 · 滚轮缩放 · 右键平移</div>
        </div>
      </div>

      <aside>
        <div className="assistant-heading"><span><Sparkles size={17} /></span><div><h2>AI 场景助手</h2><p>描述你希望看到的修改</p></div></div>
        <div className="prompt-guide"><strong>写得更准确</strong><p>说明修改对象、希望的效果和必须保持不变的部分。</p></div>
        <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：降低入口前乔木密度，改为黄昏暖色亮窗，保持建筑和运动场不变。" />
        <div className="examples">
          {examples.map((example) => <button key={example} onClick={() => setPrompt(example)}>{example}<ChevronRight size={13} /></button>)}
        </div>
        <button className="submit" disabled={busy || prompt.trim().length < 2} onClick={submit}>{busy ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}分析并保存修改</button>
        {message && <p className="message">{message}</p>}

        <div className="history-title"><div><History size={17} /><strong>最近修改</strong></div><small>保留近 5 次</small></div>
        <div className="history-list">
          {revisions.map((revision, index) => <article key={`${revision.id}-${revision.created_at}`}>
            <div className="revision-index">{index === 0 ? "当前" : revision.id}</div>
            <div className="revision-content"><strong>{revision.title}</strong><p>{revision.prompt}</p><small><Clock3 size={11} />{new Date(revision.created_at).toLocaleString("zh-CN")}</small></div>
            {index > 0 && <button title="恢复此版本" onClick={() => restore(revision.id)}><RotateCcw size={15} /></button>}
          </article>)}
        </div>
      </aside>
    </section>
  </main>;
}
