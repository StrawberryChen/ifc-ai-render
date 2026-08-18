import "@google/model-viewer";
import type { ModelViewerElement } from "@google/model-viewer";
import { createElement, useEffect, useRef } from "react";
import type { CameraView } from "./types";

export function preloadModel(modelUrl: string) {
  fetch(modelUrl, { cache: "force-cache" }).catch(() => undefined);
}

export default function ModelViewer({ modelUrl, staged, hidden = false, onViewChange }: { modelUrl: string; staged: boolean; hidden?: boolean; onViewChange?: (view: CameraView) => void }) {
  const viewer = useRef<ModelViewerElement | null>(null);
  const reportTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    const element = viewer.current;
    if (!element) return;
    const report = () => {
      window.clearTimeout(reportTimer.current);
      reportTimer.current = window.setTimeout(() => {
        const orbit = element.getCameraOrbit();
        const dimensions = element.getDimensions();
        const maximum = Math.max(dimensions.x, dimensions.y, dimensions.z, 0.001);
        onViewChange?.({
          azimuth_deg: (90 - orbit.theta * 180 / Math.PI + 360) % 360,
          elevation_deg: Math.max(8, Math.min(80, 90 - orbit.phi * 180 / Math.PI)),
          distance_multiplier: Math.max(0.75, Math.min(4, orbit.radius / maximum)),
          focal_length_mm: 45,
        });
      }, 140);
    };
    element.addEventListener("load", report);
    element.addEventListener("camera-change", report);
    if (element.loaded) report();
    return () => {
      window.clearTimeout(reportTimer.current);
      element.removeEventListener("load", report);
      element.removeEventListener("camera-change", report);
    };
  }, [modelUrl, onViewChange]);

  return <div className={`viewer-shell ${hidden ? "viewer-shell-hidden" : ""}`}>
    {createElement("model-viewer", {
      ref: (node: ModelViewerElement | null) => { viewer.current = node; },
      src: modelUrl,
      alt: staged ? "Blender staged architectural model" : "Source architectural model",
      "camera-controls": true,
      "interaction-prompt": "none",
      "camera-orbit": "35deg 67deg 115%",
      "min-camera-orbit": "auto 10deg 70%",
      "max-camera-orbit": "auto 82deg 400%",
      "shadow-intensity": "0",
      exposure: staged ? "1.05" : "1.15",
      loading: "eager",
      reveal: "auto",
    })}
  </div>;
}
