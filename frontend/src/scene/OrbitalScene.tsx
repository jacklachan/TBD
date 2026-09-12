import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { VisualizationBundle } from "../contracts";
import { currentVariant, distance } from "../workspace";
import { disposeScene, makeSatellite } from "./satellite";

export type ViewMode = "orbit" | "approach";
interface Props {
  bundle: VisualizationBundle;
  selected: string;
  sample: number;
  theme: string;
  view: ViewMode;
  debrisId: string;
  cameraReset: number;
}
const earthRadiusM = 6_371_000;
const earthURL = "/assets/earth-september.jpg";
// Right-handed display rotation: simulation XYZ -> Three.js X,Z,-Y.
const vector = (p: number[]) => new THREE.Vector3(p[0], p[2], -p[1]);

export function OrbitalScene(props: Props) {
  const host = useRef<HTMLDivElement>(null),
    satLabel = useRef<HTMLDivElement>(null),
    debrisLabel = useRef<HTMLDivElement>(null),
    distanceLabel = useRef<HTMLDivElement>(null);
  const update = useRef<((props: Props) => void) | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const element = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setFailed(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.4;
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.005, 100);
    camera.position.set(-3.1, 1.7, 2.4);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.enablePan = false;
    controls.rotateSpeed = 0.6;
    const ambient = new THREE.HemisphereLight("#bedcf1", "#101822", 1.35);
    scene.add(ambient);
    const sunlight = new THREE.DirectionalLight("#fff4db", 3.8);
    sunlight.position.set(-3, 5, 4);
    scene.add(sunlight);
    let disposed = false;
    const texture = new THREE.TextureLoader().load(earthURL, () => {
      if (disposed) texture.dispose();
    });
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    const earth = new THREE.Mesh(
      new THREE.SphereGeometry(1, 96, 64),
      new THREE.MeshStandardMaterial({
        map: texture,
        roughness: 1,
        metalness: 0,
      }),
    );
    earth.rotation.y = 1.25; // Illustrative orientation, no geographic ground-track claim.
    scene.add(earth);
    // A subtle atmospheric rim is illustrative; it is not part of separation geometry.
    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.014, 64, 48),
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.BackSide,
        uniforms: { tint: { value: new THREE.Color("#62a4c9") } },
        vertexShader:
          "varying vec3 n; varying vec3 v; void main(){vec4 p=modelViewMatrix*vec4(position,1.);n=normalize(normalMatrix*normal);v=normalize(-p.xyz);gl_Position=projectionMatrix*p;}",
        fragmentShader:
          "varying vec3 n; varying vec3 v; uniform vec3 tint; void main(){float rim=pow(1.-abs(dot(n,v)),3.);gl_FragColor=vec4(tint,rim*.38);}",
      }),
    );
    scene.add(atmosphere);
    const satellite = makeSatellite();
    scene.add(satellite);
    const debrisMaterial = new THREE.MeshStandardMaterial({
      color: "#9f9990",
      metalness: 0.8,
      roughness: 0.5,
    });
    const debris = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1, 0),
      debrisMaterial,
    );
    scene.add(debris);
    const second = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1, 0),
      debrisMaterial,
    );
    scene.add(second);
    const lineGeometry = new THREE.BufferGeometry().setAttribute(
      "position",
      new THREE.Float32BufferAttribute(new Float32Array(6), 3),
    );
    const lineMaterial = new THREE.LineBasicMaterial({
      color: "#ddac6c",
      transparent: true,
      opacity: 0.9,
    });
    const separationLine = new THREE.Line(lineGeometry, lineMaterial);
    separationLine.renderOrder = 3;
    scene.add(separationLine);
    const paths = new THREE.Group();
    scene.add(paths);
    let priorBundle: VisualizationBundle | null = null,
      priorId = "",
      priorView = "",
      priorReset = -1;
    let currentOrigin = new THREE.Vector3(),
      scale = 1 / earthRadiusM;
    let labelPositions: THREE.Vector3[] = [];

    function renderState(next: Props) {
      const variant = currentVariant(next.bundle, next.selected);
      if (!variant) return;
      const s = Math.min(next.sample, next.bundle.t_s.length - 1);
      const sat = vector(variant.positions_m[next.bundle.satellite_id][s]);
      const otherId =
        next.debrisId in variant.positions_m
          ? next.debrisId
          : next.bundle.primary_threat_id;
      const other = vector(variant.positions_m[otherId][s]);
      const modeChanged = priorView !== next.view;
      scale = next.view === "orbit" ? 1 / earthRadiusM : 0.001;
      currentOrigin =
        next.view === "orbit"
          ? new THREE.Vector3()
          : sat.clone().add(other).multiplyScalar(0.5);
      const display = (v: THREE.Vector3) =>
        v.clone().sub(currentOrigin).multiplyScalar(scale);
      satellite.position.copy(display(sat));
      debris.position.copy(display(other));
      // The generated fixtures always carry a third object, so this mesh used
      // to be unconditional. A case built from pasted elements can be just a
      // spacecraft and one other object, and reaching for a third then read
      // position samples off undefined.
      const extraId = next.bundle.object_ids.find(
        (id) => id !== otherId && id !== next.bundle.satellite_id,
      );
      second.visible = extraId !== undefined;
      if (extraId !== undefined) {
        second.position.copy(display(vector(variant.positions_m[extraId][s])));
      }
      const gap = sat.distanceTo(other) * scale;
      satellite.scale.setScalar(
        next.view === "orbit" ? 0.033 : Math.max(0.01, gap * 0.025),
      );
      debris.scale.setScalar(
        next.view === "orbit" ? 0.011 : Math.max(0.006, gap * 0.02),
      );
      second.scale.copy(debris.scale);
      // Attitude is illustrative; centre positions are the computed samples.
      satellite.rotation.set(0.45, -0.35, 0.4);
      debris.rotation.set(0.8, 0.5, 0.7);
      second.rotation.set(0.3, -0.6, 0.2);
      earth.position.copy(currentOrigin).multiplyScalar(-scale);
      earth.scale.setScalar(earthRadiusM * scale);
      atmosphere.position.copy(earth.position);
      atmosphere.scale.copy(earth.scale);
      earth.visible = atmosphere.visible = next.view === "orbit";
      ambient.intensity = next.theme === "light" ? 2.0 : 1.2;
      lineMaterial.color.set(
        variant.pair_separations_m[otherId][s] < next.bundle.min_separation_m
          ? "#eaa26f"
          : "#a1d5be",
      );
      const coordinates = lineGeometry.attributes
        .position as THREE.BufferAttribute;
      coordinates.setXYZ(0, ...satellite.position.toArray());
      coordinates.setXYZ(1, ...debris.position.toArray());
      coordinates.needsUpdate = true;
      lineGeometry.computeBoundingSphere();

      if (
        priorBundle !== next.bundle ||
        priorId !== next.selected ||
        modeChanged ||
        next.view === "approach"
      ) {
        disposeScene(paths);
        paths.clear();
        for (const id of next.bundle.object_ids) {
          const points: THREE.Vector3[] = [];
          const lower = next.view === "orbit" ? 0 : Math.max(0, s - 4);
          const upper =
            next.view === "orbit"
              ? next.bundle.t_s.length
              : Math.min(next.bundle.t_s.length, s + 5);
          for (let i = lower; i < upper; i++)
            points.push(display(vector(variant.positions_m[id][i])));
          const material = new THREE.LineBasicMaterial({
            color:
              id === next.bundle.satellite_id
                ? "#b1cfdf"
                : id === otherId
                  ? "#cc9a67"
                  : "#71858c",
            opacity: next.theme === "light" ? 0.7 : 0.48,
            transparent: true,
          });
          paths.add(
            new THREE.Line(
              new THREE.BufferGeometry().setFromPoints(points),
              material,
            ),
          );
        }
      }
      if (
        modeChanged ||
        priorReset !== next.cameraReset ||
        priorBundle === null
      ) {
        controls.target.set(0, 0, 0);
        if (next.view === "orbit") {
          camera.position.copy(
            sat
              .clone()
              .normalize()
              .multiplyScalar(3.6)
              .add(new THREE.Vector3(0.25, 0.6, 1.2)),
          );
          controls.minDistance = 1.5;
          controls.maxDistance = 8;
          camera.near = 0.005;
          camera.far = 100;
        } else {
          const along = other.clone().sub(sat).normalize();
          const normal = along.clone().cross(new THREE.Vector3(0, 1, 0));
          if (normal.lengthSq() < 0.01)
            normal.copy(along).cross(new THREE.Vector3(1, 0, 0));
          normal.normalize();
          camera.position.copy(normal.multiplyScalar(Math.max(1.2, gap * 2.7)));
          controls.minDistance = 0.15;
          controls.maxDistance = Math.max(100, gap * 10);
          camera.near = 0.001;
          camera.far = Math.max(100000, gap * 30);
        }
        camera.updateProjectionMatrix();
        controls.update();
      }
      labelPositions = [
        satellite.position.clone(),
        debris.position.clone(),
        satellite.position.clone().add(debris.position).multiplyScalar(0.5),
      ];
      priorBundle = next.bundle;
      priorId = next.selected;
      priorView = next.view;
      priorReset = next.cameraReset;
    }
    update.current = renderState;
    renderState(latest.current);
    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const lost = (event: Event) => {
      event.preventDefault();
      setFailed(true);
    };
    renderer.domElement.addEventListener("webglcontextlost", lost);
    let frame = 0;
    function draw() {
      frame = requestAnimationFrame(draw);
      if (document.hidden) return;
      controls.update();
      renderer.render(scene, camera);
      const nodes = [
        satLabel.current,
        debrisLabel.current,
        distanceLabel.current,
      ];
      const width = element.clientWidth,
        height = element.clientHeight;
      labelPositions.forEach((point, i) => {
        const node = nodes[i];
        if (!node) return;
        const projected = point.clone().project(camera);
        const behindEarth =
          latest.current.view === "orbit" &&
          point.dot(camera.position.clone().normalize()) < 0.15;
        node.style.visibility =
          projected.z > 1 ||
          projected.z < -1 ||
          behindEarth ||
          Math.abs(projected.x) > 1 ||
          Math.abs(projected.y) > 1
            ? "hidden"
            : "visible";
        node.style.transform = `translate(${(projected.x * 0.5 + 0.5) * width}px,${(-projected.y * 0.5 + 0.5) * height}px)`;
      });
    }
    draw();
    return () => {
      disposed = true;
      update.current = null;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      disposeScene(scene);
      texture.dispose();
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);
  useEffect(() => {
    update.current?.(props);
  }, [
    props.bundle,
    props.selected,
    props.sample,
    props.theme,
    props.view,
    props.debrisId,
    props.cameraReset,
  ]);
  const v = currentVariant(props.bundle, props.selected);
  const [d, u] = distance(
    v?.pair_separations_m[props.debrisId]?.[props.sample],
  );
  return (
    <div className={`orbital-scene ${failed ? "scene-failed" : ""}`}>
      <div
        ref={host}
        className="scene-canvas"
        data-testid="orbital-canvas"
        aria-label="Interactive 3D orbital scene. Drag to rotate, scroll to zoom."
      />
      {!failed && (
        <div className="scene-labels" aria-hidden="true">
          <div ref={satLabel} className="projected-label satellite-label">
            <span>
              <i />
              NOAA 20
            </span>
          </div>
          <div ref={debrisLabel} className="projected-label debris-label">
            <span>
              <i />
              {props.debrisId}
            </span>
          </div>
          <div ref={distanceLabel} className="projected-label distance-label">
            <span>
              {d} <small>{u}</small>
            </span>
          </div>
        </div>
      )}
      {failed && (
        <div className="webgl-fallback glass">
          <h2>3D is unavailable on this device.</h2>
          <p>
            The distance chart, exact time controls, and all numerical checks
            remain available.
          </p>
        </div>
      )}
    </div>
  );
}

export function SatellitePreview() {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene(),
      model = makeSatellite();
    model.rotation.set(0.3, -0.25, -0.24);
    scene.add(model);
    scene.add(new THREE.HemisphereLight("#d9ecff", "#36322a", 2.8));
    const lamp = new THREE.DirectionalLight("#fff3d5", 4);
    lamp.position.set(2, 4, 6);
    scene.add(lamp);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 1.6, 10.8);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.enableDamping = true;
    element.appendChild(renderer.domElement);
    const resize = () => {
      renderer.setSize(element.clientWidth, element.clientHeight);
      camera.aspect = element.clientWidth / Math.max(1, element.clientHeight);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    let frame = 0;
    const draw = () => {
      frame = requestAnimationFrame(draw);
      if (!document.hidden) {
        controls.update();
        renderer.render(scene, camera);
      }
    };
    draw();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      disposeScene(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);
  return (
    <div
      className="satellite-preview"
      ref={host}
      role="img"
      aria-label="Drag to inspect the illustrative spacecraft model"
    />
  );
}
