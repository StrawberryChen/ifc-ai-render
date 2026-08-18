import { Canvas, useThree } from "@react-three/fiber";
import { Grid, OrbitControls, useGLTF, useProgress } from "@react-three/drei";
import { Box3, Object3D, Vector3 } from "three";
import { Component, Suspense, useCallback, useEffect, useMemo, useRef } from "react";
import type { CameraView } from "./types";

function SceneModel({ modelUrl }: { modelUrl: string }) {
  const gltf = useGLTF(modelUrl);
  const object = useMemo<Object3D>(() => gltf.scene.clone(true), [gltf.scene]);
  useEffect(() => {
    const contextObjects: Array<{ child: Object3D; parent: Object3D }> = [];
    object.traverse((child) => {
      if (child.name.startsWith("AIR_Context") && child.parent) {
        contextObjects.push({ child, parent: child.parent });
      }
    });
    contextObjects.forEach(({ child, parent }) => parent.remove(child));
    const bounds = new Box3().setFromObject(object);
    contextObjects.forEach(({ child, parent }) => parent.add(child));
    const center = bounds.getCenter(new Vector3());
    const size = bounds.getSize(new Vector3());
    const scale = 7 / Math.max(size.x, size.y, size.z, 0.001);
    object.position.set(-center.x * scale, -bounds.min.y * scale, -center.z * scale);
    object.scale.setScalar(scale);
    object.traverse((child) => { child.castShadow = true; child.receiveShadow = true; });
  }, [object]);
  return <primitive object={object} />;
}

function LoadingIndicator() {
  const { progress } = useProgress();
  return <div className="viewer-state"><span className="viewer-loader" /><strong>正在载入三维场景 {Math.round(progress)}%</strong><small>读取 GLB 模型与嵌入贴图</small></div>;
}

class ViewerErrorBoundary extends Component<{ children: React.ReactNode }, { error: string }> {
  state = { error: "" };
  static getDerivedStateFromError(error: Error) { return { error: error.message }; }
  render() {
    if (this.state.error) return <div className="viewer-state error"><strong>三维模型载入失败</strong><small>{this.state.error}</small></div>;
    return this.props.children;
  }
}

function ViewControls({ onViewChange }: { onViewChange?: (view: CameraView) => void }) {
  const controls = useRef<any>(null);
  const { camera } = useThree();
  const report = useCallback(() => {
    const target = controls.current?.target ?? new Vector3(0, 1.4, 0);
    const offset = camera.position.clone().sub(target);
    const horizontal = Math.hypot(offset.x, offset.z);
    onViewChange?.({
      azimuth_deg: (Math.atan2(-offset.z, offset.x) * 180 / Math.PI + 360) % 360,
      elevation_deg: Math.max(8, Math.min(80, Math.atan2(offset.y, horizontal) * 180 / Math.PI)),
      distance_multiplier: Math.max(0.75, Math.min(4, offset.length() / 7)),
      focal_length_mm: 45,
    });
  }, [camera, onViewChange]);
  useEffect(() => { report(); }, [report]);
  return <OrbitControls ref={controls} makeDefault target={[0, 1.4, 0]} minDistance={5.25} maxDistance={28} onEnd={report} />;
}

export default function ModelViewer({ modelUrl, staged, onViewChange }: { modelUrl: string; staged: boolean; onViewChange?: (view: CameraView) => void }) {
  return <div className="viewer-shell">
    <ViewerErrorBoundary>
      <Suspense fallback={<LoadingIndicator />}>
        <Canvas camera={{ position: [8, 5.5, 9], fov: 42 }} shadows dpr={[1, 1.75]}>
          <color attach="background" args={[staged ? "#18201e" : "#e8e5de"]} />
          <ambientLight intensity={staged ? 0.7 : 1.5} />
          <hemisphereLight color="#dcecff" groundColor="#4b554c" intensity={staged ? 1.1 : 0.8} />
          <directionalLight position={[8, 12, 6]} intensity={staged ? 2.4 : 1.7} castShadow />
          <SceneModel modelUrl={modelUrl} />
          {!staged && <Grid position={[0, -0.01, 0]} args={[40, 40]} cellColor="#c7c2b8" sectionColor="#a8a196" fadeDistance={25} />}
          <ViewControls onViewChange={onViewChange} />
        </Canvas>
      </Suspense>
    </ViewerErrorBoundary>
  </div>;
}
