import * as THREE from "three";

/** A camera-facing text label as a Three.js sprite (canvas texture). */
export function makeLabel(text: string, color = "#dfe6f5"): THREE.Sprite {
  const pad = 8;
  const font = 28;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  ctx.font = `${font}px system-ui, sans-serif`;
  const w = Math.ceil(ctx.measureText(text).width) + pad * 2;
  const h = font + pad * 2;
  canvas.width = w;
  canvas.height = h;
  ctx.font = `${font}px system-ui, sans-serif`;
  ctx.fillStyle = "rgba(8,12,22,0.72)";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = color;
  ctx.textBaseline = "middle";
  ctx.fillText(text, pad, h / 2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.minFilter = THREE.LinearFilter;
  const mat = new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set((w / h) * 0.06, 0.06, 1); // scaled again per-use via .scale multiply
  sprite.userData.aspect = w / h;
  return sprite;
}
