// The black entity: a deliberately simple, slightly-desarticulated silhouette
// built from primitives. No face, no detail: the threat is shape and motion.
import * as THREE from 'three';

const BODY_MAT = new THREE.MeshStandardMaterial({ color: 0x040404, roughness: 0.95, metalness: 0.0 });
const RIM_MAT = new THREE.MeshBasicMaterial({ color: 0x141414, side: THREE.BackSide });

function angleLerp(a, b, t) {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

export function createEntityMesh() {
  const group = new THREE.Group();

  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.95, 0.26), BODY_MAT);
  torso.position.y = 1.1;
  torso.rotation.z = 0.03;
  group.add(torso);

  const head = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.28, 0.24), BODY_MAT);
  head.position.set(0.02, 1.78, 0.01);
  head.rotation.x = 0.08;
  group.add(head);

  const legL = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.9, 0.18), BODY_MAT);
  legL.position.set(-0.13, 0.45, 0);
  const legR = legL.clone();
  legR.position.x = 0.13;
  legR.rotation.x = 0.05;
  group.add(legL, legR);

  const armL = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.82, 0.13), BODY_MAT);
  armL.position.set(-0.3, 1.05, 0.03);
  armL.rotation.z = 0.18;
  const armR = armL.clone();
  armR.position.x = 0.3;
  armR.rotation.z = -0.22;
  group.add(armL, armR);

  // Cheap outline: a slightly inflated backface duplicate so the silhouette
  // stays readable against very dark backgrounds without any custom shader.
  for (const part of [torso, head, legL, legR, armL, armR]) {
    const rim = new THREE.Mesh(part.geometry, RIM_MAT);
    rim.scale.setScalar(1.06);
    part.add(rim);
  }

  group.userData.legs = [legL, legR];
  group.userData.walkPhase = 0;
  group.visible = false;
  return group;
}

/** Interpolates render position between the entity's previous and current fixed-step pose. */
export function updateEntityMesh(mesh, entity, alpha, dt) {
  mesh.visible = true;
  mesh.position.x = entity.prevX + (entity.x - entity.prevX) * alpha;
  mesh.position.z = entity.prevZ + (entity.z - entity.prevZ) * alpha;
  mesh.rotation.y = angleLerp(mesh.rotation.y, entity.facing, 0.35);

  const speed = Math.hypot(entity.x - entity.prevX, entity.z - entity.prevZ);
  const moving = speed > 0.0005;
  mesh.userData.walkPhase += (moving ? 10 : 0) * Math.max(dt, 0);
  const swing = moving ? Math.sin(mesh.userData.walkPhase) * 0.35 : 0;
  const [legL, legR] = mesh.userData.legs;
  legL.rotation.x = swing;
  legR.rotation.x = -swing;
}

export function disposeEntityMesh(mesh) {
  mesh.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
}
