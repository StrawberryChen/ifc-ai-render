import { Canvas, useLoader } from "@react-three/fiber";
import { Grid, OrbitControls } from "@react-three/drei";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { Box3, TextureLoader, Mesh, MeshStandardMaterial, SRGBColorSpace, Vector3 } from "three";
import { Suspense, useEffect, useMemo } from "react";

function Building({ modelUrl, textureUrl, staged }: { modelUrl: string; textureUrl: string; staged: boolean }) {
  const source = useLoader(OBJLoader, modelUrl);
  const texture = useLoader(TextureLoader, textureUrl);
  const object = useMemo(() => source.clone(), [source]);
  texture.colorSpace = SRGBColorSpace;
  useEffect(() => {
    object.traverse((child) => {
      if (child instanceof Mesh) {
        child.material = new MeshStandardMaterial({
          map: staged ? texture : null,
          color: staged ? "#ffffff" : "#d9d5cb",
          roughness: staged ? 0.58 : 0.9,
          metalness: 0.02,
        });
      }
    });
    const bounds = new Box3().setFromObject(object);
    const center = bounds.getCenter(new Vector3());
    const size = bounds.getSize(new Vector3());
    const scale = 7 / Math.max(size.x, size.y, size.z);
    object.position.set(-center.x * scale, -bounds.min.y * scale, -center.z * scale);
    object.scale.setScalar(scale);
  }, [object, staged, texture]);
  return <primitive object={object} />;
}

export default function ModelViewer(props: { modelUrl: string; textureUrl: string; staged: boolean }) {
  return <Canvas camera={{ position: [8, 5.5, 9], fov: 42 }} shadows>
    <color attach="background" args={[props.staged ? "#18201e" : "#e8e5de"]} />
    <ambientLight intensity={props.staged ? 0.7 : 1.6} />
    <hemisphereLight color="#dcecff" groundColor="#4b554c" intensity={props.staged ? 1.2 : 0.8} />
    <directionalLight position={[8, 12, 6]} intensity={props.staged ? 2.6 : 1.8} castShadow />
    <mesh position={[0, -0.08, 0]} receiveShadow>
      <boxGeometry args={[16, 0.12, 16]} />
      <meshStandardMaterial color={props.staged ? "#26342c" : "#d6d2c9"} />
    </mesh>
    <Suspense fallback={null}>
      <Building {...props} />
    </Suspense>
    <Grid position={[0, -0.02, 0]} args={[80, 80]} cellColor={props.staged ? "#33413a" : "#c7c2b8"} sectionColor={props.staged ? "#597062" : "#a8a196"} fadeDistance={45} />
    <OrbitControls makeDefault />
  </Canvas>;
}
