import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { Box, Camera, ChevronRight, Clock3, History, Image, LoaderCircle, RotateCcw, Send, Sparkles, TriangleAlert } from "lucide-react";
import ModelViewer, { preloadModel } from "./ModelViewer";
import { API, getProject, getRevisions, renderCameraView, restoreRevision, submitPrompt } from "./api";
import type { CameraView, Project, Revision } from "./types";

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
  const [cameraView, setCameraView] = useState<CameraView | null>(null);
  const [viewerTab, setViewerTab] = useState<"source" | "staged">("source");

  const refresh = async () => {
    const [nextProject, nextRevisions] = await Promise.all([getProject(), getRevisions()]);
    setProject(nextProject); setRevisions(nextRevisions);
  };
  useEffect(() => { refresh().catch(() => setMessage("本地服务尚未启动，请检查 FastAPI。")); }, []);
  useEffect(() => {
    if (!project) return;
    preloadModel(`${API}${project.source_model_url}?viewer=2`);
    preloadModel(`${API}${project.staged_model_url}?v=${revisions[0]?.number ?? 0}&viewer=2`);
  }, [project, revisions]);
  useEffect(() => {
    if (tab !== "render") setViewerTab(tab);
  }, [tab]);
  useEffect(() => {
    if (revisions[0]?.status !== "rendering") return;
    const timer = window.setInterval(() => refresh().catch(() => undefined), 1800);
    return () => window.clearInterval(timer);
  }, [revisions]);

  const submit = async () => {
    if (prompt.trim().length < 2) return;
    setBusy(true); setMessage("");
    try { const result = await submitPrompt(prompt); setMessage(result.message); setPrompt(""); setTab("render"); await refresh(); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  };

  const currentRevision = revisions[0];
  const stagedVersion = currentRevision?.number ?? 0;
  const currentPreview = currentRevision?.status === "ready" ? currentRevision.preview_url : project?.render_preview_url;

  const restore = async (id: string) => {
    setBusy(true);
    try { await restoreRevision(id); await refresh(); setMessage(`已从 ${id} 创建新的恢复版本。`); }
    finally { setBusy(false); }
  };

  const renderSelectedView = async () => {
    if (!cameraView) return;
    setBusy(true); setMessage("");
    try {
      const result = await renderCameraView(cameraView);
      setMessage(result.message); setTab("render"); await refresh();
    } catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  };

  return <main>
    <header>
      <div className="brand"><span className="brand-mark"><Box size={19} /></span><div><strong>FormRender</strong><small>建筑可视化工作台</small></div></div>
      <div className="project-title"><span className="status-dot" />{project?.name ?? "正在连接项目…"}</div>
      <button className="render-button" onClick={() => setTab("render")}><Image size={16} />查看最新预览</button>
    </header>

    <section className="workspace">
      <div className="stage-panel">
        <nav className="view-tabs">
          <button className={tab === "source" ? "active" : ""} onClick={() => setTab("source")}><Box size={15} />原始模型</button>
          <button className={tab === "staged" ? "active" : ""} onClick={() => setTab("staged")}><Sparkles size={15} />布景模型</button>
          <button className={tab === "render" ? "active" : ""} onClick={() => setTab("render")}><Image size={15} />渲染预览</button>
        </nav>
        <div className="viewport">
          {project && <ModelViewer hidden={tab === "render"} modelUrl={`${API}${viewerTab === "source" ? project.source_model_url : project.staged_model_url}${viewerTab === "staged" ? `?v=${stagedVersion}&viewer=2` : "?viewer=2"}`} staged={viewerTab === "staged"} onViewChange={viewerTab === "staged" ? setCameraView : undefined} />}
          {project && tab === "render" && currentPreview && <div className="render-frame" style={{ "--preview-image": `url(${API}${currentPreview}?v=${stagedVersion})` } as CSSProperties}><img className="render-preview" src={`${API}${currentPreview}?v=${stagedVersion}`} alt="Blender render preview" /></div>}
          {!project && <div className="loading"><LoaderCircle className="spin" />连接本地项目…</div>}
          {currentRevision?.status === "rendering" && <div className="render-status"><LoaderCircle className="spin" size={18} /><div><strong>Blender 正在生成预览</strong><small>完成后会自动更新当前画面</small></div></div>}
          {currentRevision?.status === "failed" && <div className="render-status failed"><TriangleAlert size={18} /><div><strong>本次预览失败</strong><small>{currentRevision.error ?? "请检查 Blender 执行日志"}</small></div></div>}
          {tab === "staged" && cameraView && <div className="camera-capture"><div><strong>当前三维视角</strong><small>方位 {cameraView.azimuth_deg.toFixed(0)}° · 俯角 {cameraView.elevation_deg.toFixed(0)}°</small></div><button onClick={renderSelectedView} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <Camera size={15} />}设为渲染视角</button></div>}
          <div className="viewport-hint">拖动旋转 · 滚轮缩放 · 右键平移</div>
        </div>
      </div>

      <aside>
        <div className="assistant-heading"><span><Sparkles size={17} /></span><div><h2>AI 场景助手</h2><p>描述你希望看到的修改</p></div><em className={`planner-mode ${project?.planner_mode}`}>{project?.planner_mode === "deepseek" ? "DeepSeek" : "本地规则"}</em></div>
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
            <div className={`revision-index ${revision.status}`}>{revision.status === "rendering" ? <LoaderCircle className="spin" size={12} /> : index === 0 ? "当前" : revision.id}</div>
            <div className="revision-content"><strong>{revision.title}</strong><p>{revision.prompt}</p>{revision.actions?.length ? <div className="action-count">{revision.actions.length} 个受控动作 · {revision.planner}</div> : null}<small><Clock3 size={11} />{new Date(revision.created_at).toLocaleString("zh-CN")}</small></div>
            {index > 0 && <button title="恢复此版本" onClick={() => restore(revision.id)}><RotateCcw size={15} /></button>}
          </article>)}
        </div>
      </aside>
    </section>
  </main>;
}
