import "./style.css";
import { FRAMES, type FrameId, type PointKey, Viewer, type Selectable } from "./render/viewer";
import { SimClock } from "./sim/time";
import { type PresetId, PRESETS, World, makePreset } from "./sim/world";

const canvas = document.getElementById("scene") as HTMLCanvasElement;
const world = new World();
const clock = new SimClock(Date.now());
const viewer = new Viewer(canvas, world);

// ----------------------------------------------------------- frame navigation
const frameButtons = document.getElementById("frame-buttons")!;
const frameHint = document.getElementById("frame-hint")!;
let activeFrame: FrameId = "sun";
for (const f of FRAMES) {
  const b = document.createElement("button");
  b.textContent = f.label;
  b.onclick = () => {
    activeFrame = f.id;
    viewer.setFrame(f.id);
    frameHint.textContent = f.hint;
    for (const el of frameButtons.children) el.classList.toggle("active", el === b);
  };
  if (f.id === activeFrame) b.classList.add("active");
  frameButtons.appendChild(b);
}
frameHint.textContent = FRAMES[0].hint;

// --------------------------------------------------------------- time controls
const playBtn = document.getElementById("play") as HTMLButtonElement;
const nowBtn = document.getElementById("now") as HTMLButtonElement;
const rate = document.getElementById("rate") as HTMLInputElement;
const rateLabel = document.getElementById("rate-label")!;
const epoch = document.getElementById("epoch")!;

function humanRate(secPerSec: number): string {
  const a = Math.abs(secPerSec);
  const sign = secPerSec < 0 ? "−" : "";
  if (a < 60) return `${sign}${a.toFixed(0)} s/s`;
  if (a < 3600) return `${sign}${(a / 60).toFixed(1)} min/s`;
  if (a < 86400) return `${sign}${(a / 3600).toFixed(1)} h/s`;
  return `${sign}${(a / 86400).toFixed(1)} j/s`;
}
function applyRate() {
  const x = parseFloat(rate.value);
  clock.rate = Math.sign(x) * Math.pow(10, Math.abs(x));
  if (x === 0) clock.rate = 0;
  rateLabel.textContent = humanRate(clock.rate);
}
rate.oninput = applyRate;
applyRate();

playBtn.onclick = () => {
  clock.running = !clock.running;
  playBtn.textContent = clock.running ? "⏸︎ Pause" : "▶ Lecture";
};
nowBtn.onclick = () => clock.setDate(Date.now());

// ------------------------------------------------------------- point toggles
const pointToggles = document.getElementById("point-toggles")!;
const POINTS: { key: PointKey; label: string; on: boolean }[] = [
  { key: "geo", label: "GEO (géostationnaire)", on: true },
  { key: "lunastat", label: "Sélénostationnaire", on: true },
  { key: "lagrange-em", label: "Lagrange Terre–Lune", on: true },
  { key: "lagrange-se", label: "Lagrange Soleil–Terre", on: false },
];
for (const p of POINTS) {
  const id = `pt-${p.key}`;
  const wrap = document.createElement("label");
  wrap.className = "check";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.id = id;
  cb.checked = p.on;
  cb.onchange = () => viewer.setPointVisible(p.key, cb.checked);
  viewer.setPointVisible(p.key, p.on);
  wrap.append(cb, document.createTextNode(" " + p.label));
  pointToggles.appendChild(wrap);
}

// --------------------------------------------------------------- satellites
const presetSel = document.getElementById("sat-preset") as HTMLSelectElement;
const addBtn = document.getElementById("sat-add") as HTMLButtonElement;
const satList = document.getElementById("sat-list")!;
for (const p of PRESETS) {
  const opt = document.createElement("option");
  opt.value = p.id;
  opt.textContent = p.label;
  presetSel.appendChild(opt);
}
function renderSatList() {
  satList.innerHTML = "";
  for (const s of world.satellites) {
    const li = document.createElement("li");
    const dot = `<span class="dot" style="background:#${s.color.toString(16).padStart(6, "0")}"></span>`;
    li.innerHTML = `${dot}<span class="sat-name">${s.name}</span>`;
    const del = document.createElement("button");
    del.textContent = "✕";
    del.title = "Retirer";
    del.onclick = () => {
      world.remove(s.id);
      renderSatList();
    };
    li.appendChild(del);
    satList.appendChild(li);
  }
}
addBtn.onclick = () => {
  world.add(makePreset(presetSel.value as PresetId, clock.tSecJ2000));
  renderSatList();
};

// ------------------------------------------------------------------ selection
const info = document.getElementById("info")!;
viewer.onSelect = (sel: Selectable | null) => {
  if (!sel) {
    info.textContent = "—";
    return;
  }
  const kind = { body: "Corps", satellite: "Satellite", point: "Point" }[sel.kind];
  info.innerHTML = `<strong>${sel.name}</strong> <em>(${kind})</em>${sel.note ? `<br>${sel.note}` : ""}`;
};

// Seed a couple of satellites so the scene is alive on first load.
world.add(makePreset("geo", clock.tSecJ2000));
world.add(makePreset("nrho", clock.tSecJ2000));
renderSatList();

// --------------------------------------------------------------- main loop
addEventListener("resize", () => viewer.resize());
let last = performance.now();
function loop(now: number) {
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;
  clock.advance(dt);
  epoch.textContent = clock.date.toISOString().slice(0, 19).replace("T", " ") + " UTC";
  viewer.update(clock.tSecJ2000);
  viewer.render();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
