import { Canvas } from "@react-three/fiber";
import { Grid, OrbitControls, useGLTF, useProgress } from "@react-three/drei";
import { Box3, Object3D, Vector3 } from "three";
import { Component, Suspense, useEffect, useMemo } from "react";

function SceneModel({ modelUrl }: { modelUrl: string }) {
  const gltf = useGLTF(modelUrl);
  const object = useMemo<Object3D>(() => gltf.scene.clone(true), [gltf.scene]);
  useEffect(() => {
    const renderOnlyContext = object.getObjectByName("AIR_ContextGround");
    if (renderOnlyContext?.parent) renderOnlyContext.parent.remove(renderOnlyContext);
    const bounds = new Box3().setFromObject(object);
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

export default function ModelViewer({ modelUrl, staged }: { modelUrl: string; staged: boolean }) {
  return <div className="viewer-shell">
    <ViewerErrorBoundary>
      <Suspense fallback={<LoadingIndicator />}>
        <Canvas camera={{ position: [8, 5.5, 9], fov: 42 }} shadows dpr={[1, 1.75]}>
          <color attach="background" args={[staged ? "#18201e" : "#e8e5de"]} />
          <ambientLight intensity={staged ? 0.7 : 1.5} />
          <hemisphereLight color="#dcecff" groundColor="#4b554c" intensity={staged ? 1.1 : 0.8} />
          <directionalLight position={[8, 12, 6]} intensity={staged ? 2.4 : 1.7} castShadow />
          <SceneModel modelUrl={modelUrl} />
          <Grid position={[0, -0.01, 0]} args={[40, 40]} cellColor={staged ? "#33413a" : "#c7c2b8"} sectionColor={staged ? "#597062" : "#a8a196"} fadeDistance={25} />
          <OrbitControls makeDefault target={[0, 1.4, 0]} minDistance={4} maxDistance={24} />
        </Canvas>
      </Suspense>
    </ViewerErrorBoundary>
  </div>;
}
