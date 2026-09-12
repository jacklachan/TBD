import * as THREE from "three";

/** Original illustrative spacecraft. Mesh dimensions never enter the physics. */
export function makeSatellite(): THREE.Group {
  const group = new THREE.Group();
  const gold = new THREE.MeshStandardMaterial({
    color: "#c7a05a",
    metalness: 0.78,
    roughness: 0.36,
  });
  const silver = new THREE.MeshStandardMaterial({
    color: "#c3ced4",
    metalness: 0.65,
    roughness: 0.28,
  });
  const dark = new THREE.MeshStandardMaterial({
    color: "#131b24",
    metalness: 0.6,
    roughness: 0.4,
  });
  const solar = new THREE.MeshStandardMaterial({
    color: "#163b63",
    metalness: 0.8,
    roughness: 0.25,
    side: THREE.DoubleSide,
  });
  const cell = new THREE.LineBasicMaterial({
    color: "#6488a5",
    transparent: true,
    opacity: 0.66,
  });
  const box = (
    x: number,
    y: number,
    z: number,
    w: number,
    h: number,
    d: number,
    material: THREE.Material,
  ) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    group.add(mesh);
    return mesh;
  };
  box(0, 0, 0, 0.95, 1.25, 0.9, gold);
  box(0, 0.66, 0, 1.04, 0.08, 1, silver);
  box(0, -0.65, 0, 1.04, 0.08, 1, silver);
  box(0, -0.1, 0.475, 0.72, 0.62, 0.07, dark);
  for (const x of [-0.45, 0.45]) box(x, 0, 0.47, 0.045, 1.2, 0.04, silver);
  for (const side of [-1, 1]) {
    box(side * 0.85, 0, 0, 0.8, 0.07, 0.08, silver);
    for (let panel = 0; panel < 3; panel++) {
      const center = side * (1.28 + panel * 0.79);
      box(center, 0, 0, 0.77, 1.6, 0.06, silver);
      box(center, 0, 0.039, 0.7, 1.52, 0.025, solar);
      const vertices = [];
      for (let row = 1; row < 10; row++)
        vertices.push(
          center - 0.35,
          -0.76 + row * 0.152,
          0.057,
          center + 0.35,
          -0.76 + row * 0.152,
          0.057,
        );
      for (let col = 1; col < 4; col++)
        vertices.push(
          center - 0.35 + col * 0.175,
          -0.76,
          0.057,
          center - 0.35 + col * 0.175,
          0.76,
          0.057,
        );
      const lines = new THREE.LineSegments(
        new THREE.BufferGeometry().setAttribute(
          "position",
          new THREE.Float32BufferAttribute(vertices, 3),
        ),
        cell,
      );
      group.add(lines);
    }
  }
  const dish = new THREE.Mesh(
    new THREE.SphereGeometry(0.43, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.4),
    silver,
  );
  dish.position.set(0.22, 0.83, 0.12);
  dish.rotation.x = -0.65;
  group.add(dish);
  const lens = new THREE.Mesh(
    new THREE.CylinderGeometry(0.17, 0.21, 0.32, 24),
    dark,
  );
  lens.position.set(-0.22, 0.84, -0.18);
  group.add(lens);
  for (const x of [-0.32, 0.32]) {
    const nozzle = new THREE.Mesh(
      new THREE.CylinderGeometry(0.09, 0.16, 0.24, 16, 1, true),
      dark,
    );
    nozzle.position.set(x, -0.8, 0);
    group.add(nozzle);
  }
  const boom = new THREE.Mesh(
    new THREE.CylinderGeometry(0.014, 0.014, 1.4, 8),
    silver,
  );
  boom.position.set(-0.25, 1.29, -0.2);
  boom.rotation.z = 0.25;
  group.add(boom);
  return group;
}

export function disposeScene(scene: THREE.Object3D) {
  const geometries = new Set<THREE.BufferGeometry>(),
    materials = new Set<THREE.Material>();
  scene.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (mesh.geometry) geometries.add(mesh.geometry);
    if (mesh.material)
      for (const mat of Array.isArray(mesh.material)
        ? mesh.material
        : [mesh.material])
        materials.add(mat);
  });
  geometries.forEach((g) => g.dispose());
  materials.forEach((m) => m.dispose());
}
