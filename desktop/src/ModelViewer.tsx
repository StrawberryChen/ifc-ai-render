import "@google/model-viewer";
import type { ModelViewerElement } from "@google/model-viewer";
import { createElement, useEffect, useRef, useState } from "react";
import type { CameraView } from "./types";

type SavedViewerCamera = { orbit: string; target: string; fieldOfView: string };
const savedCameras: Partial<Record<"source" | "staged", SavedViewerCamera>> = {};

export function preloadModel(modelUrl: string) {
  fetch(modelUrl, { cache: "force-cache" }).catch(() => undefined);
}

export default function ModelViewer({ modelUrl, staged, hidden = false, environmentUrl, referenceRadius, onReferenceRadius, onViewChange }: { modelUrl: string; staged: boolean; hidden?: boolean; environmentUrl?: string; referenceRadius?: number; onReferenceRadius?: (radius: number) => void; onViewChange?: (view: CameraView) => void }) {
  const viewer = useRef<ModelViewerElement | null>(null);
  const reportTimer = useRef<number | undefined>(undefined);
  const [progress, setProgress] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const element = viewer.current;
    if (!element) return;
    setProgress(0); setLoaded(false); setError("");
    const report = () => {
      window.clearTimeout(reportTimer.current);
      reportTimer.current = window.setTimeout(() => {
        const orbit = element.getCameraOrbit();
        const target = element.getCameraTarget();
        const dimensions = element.getDimensions();
        const designRadius = Math.max(dimensions.x, dimensions.z, dimensions.y * 2, 0.001);
        if (!staged) onReferenceRadius?.(designRadius);
        const distanceBasis = referenceRadius ?? designRadius;
        const verticalFov = element.getFieldOfView() * Math.PI / 180;
        const aspect = Math.max(element.clientWidth / Math.max(element.clientHeight, 1), 0.1);
        const focalLength = 36 / (2 * Math.tan(verticalFov / 2) * aspect);
        savedCameras[staged ? "staged" : "source"] = {
          orbit: orbit.toString(),
          target: target.toString(),
          fieldOfView: `${element.getFieldOfView()}deg`,
        };
        onViewChange?.({
          azimuth_deg: (orbit.theta * 180 / Math.PI - 90 + 360) % 360,
          elevation_deg: Math.max(8, Math.min(80, 90 - orbit.phi * 180 / Math.PI)),
          distance_multiplier: Math.max(0.25, Math.min(12, orbit.radius / distanceBasis)),
          focal_length_mm: Math.max(18, Math.min(120, focalLength)),
        });
      }, 140);
    };
    const load = () => { setProgress(1); setLoaded(true); report(); };
    const progressEvent = (event: Event) => {
      setProgress((event as CustomEvent<{ totalProgress: number }>).detail.totalProgress);
    };
    const fail = () => setError("新的三维模型解析失败");
    element.addEventListener("load", load);
    element.addEventListener("progress", progressEvent);
    element.addEventListener("camera-change", report);
    element.addEventListener("error", fail);
    if (element.loaded) load();
    return () => {
      window.clearTimeout(reportTimer.current);
      element.removeEventListener("load", load);
      element.removeEventListener("progress", progressEvent);
      element.removeEventListener("camera-change", report);
      element.removeEventListener("error", fail);
    };
  }, [modelUrl, staged, referenceRadius, onReferenceRadius, onViewChange]);

  const savedCamera = savedCameras[staged ? "staged" : "source"];

  return <div className={`viewer-shell ${hidden ? "viewer-shell-hidden" : ""}`}>
    {createElement("model-viewer", {
      key: modelUrl,
      ref: (node: ModelViewerElement | null) => { viewer.current = node; },
      src: modelUrl,
      alt: staged ? "Blender staged architectural model" : "Source architectural model",
      "camera-controls": true,
      "interaction-prompt": "none",
      "camera-orbit": savedCamera?.orbit ?? (staged ? "35deg 67deg 38%" : "35deg 67deg 85%"),
      "camera-target": savedCamera?.target ?? "auto auto auto",
      "field-of-view": savedCamera?.fieldOfView ?? "45deg",
      "min-camera-orbit": "auto 8deg 5%",
      "max-camera-orbit": "auto 86deg 500%",
      "shadow-intensity": "0",
      exposure: staged ? "1.05" : "1.15",
      "environment-image": staged && environmentUrl ? environmentUrl : undefined,
      "skybox-image": staged && environmentUrl ? environmentUrl : undefined,
      loading: "eager",
      reveal: "auto",
    })}
    {!loaded && !error && <div className={`viewer-state ${staged ? "staged" : ""}`}><span className="viewer-loader" /><strong>正在载入{staged ? "布景" : "原始"}模型 {Math.round(progress * 100)}%</strong><small>{progress < 1 ? "下载预览模型并解析材质" : "正在准备三维场景"}</small></div>}
    {error && <div className="viewer-state error"><strong>{error}</strong><small>{modelUrl}</small></div>}
  </div>;
}
