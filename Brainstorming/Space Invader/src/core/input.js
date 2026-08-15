// Entrees du joueur : clavier (AZERTY et QWERTY par les codes physiques),
// souris (pointerlock + molette) et manette (Gamepad API).
//
// Le module ne connait rien du vaisseau : il produit seulement des axes
// normalises et des boutons. Aucune allocation par frame.
//
// ---------------------------------------------------------------------------
// TABLE DES COMMANDES (event.code = touche PHYSIQUE, donc AZERTY et QWERTY
// fonctionnent avec une seule table : en AZERTY, KeyW est la touche "Z" et
// KeyA la touche "Q", donc KeyW/KeyA/KeyS/KeyD = ZQSD).
//
//   touche AZERTY    | code            | effet
//   -----------------+-----------------+--------------------------------------
//   Z                | KeyW            | descendre       (pitch = -1)
//   S                | KeyS            | monter          (pitch = +1)
//   Q                | KeyA            | tourner a gauche (yaw = +1)
//   D                | KeyD            | tourner a droite (yaw = -1)
//   Espace           | Space           | poussee         (thrust = +1)
//   fleches          | Arrow*          | idem, mais fleche haut = monter
//   A / E            | KeyQ / KeyE     | roulis gauche / droite (facultatif)
//   Maj              | ShiftLeft/Right | postcombustion, vitesse pulse dans le vide
//   Ctrl ou X        | Control* / KeyX | freins
//   F                | KeyF            | analyser
//   C                | KeyC            | aligner le nez sur la cible (maintenu)
//   T / R            | KeyT / KeyR     | cible de navigation suivante / precedente
//                    |                 | (gerees par src/main.js)
//   J                | KeyJ            | saut hyperspatial
//   M                | KeyM            | afficher les orbites
//   V                | KeyV            | changement de camera
//   L                | KeyL            | atterrissage
//   H                | KeyH            | aide
//   G                | KeyG            | panneau de reglages
//
// Les axes `strafe` et `vertical` existent toujours dans l'API (le contrat les
// prevoit) mais aucune touche ne les alimente : le pilotage tient en 5 touches.
//
//   souris (pointerlock actif, ou bouton maintenu) : mouvement -> pitch/yaw
//   molette : axe .zoom amorti (-1..1)
//   manette : stick gauche -> pitch/yaw, stick droit -> roulis,
//             gachette droite -> poussee, gachette gauche -> frein,
//             zone morte 0.12
// ---------------------------------------------------------------------------

import { SHIP } from './settings.js';
import { clamp, damp } from './math.js';

// Vitesse de rampe des axes clavier, en unites d'axe par seconde.
const AXIS_RAMP = 8;
const DEADZONE = 0.12;
const ZOOM_DAMP = 6;
const ZOOM_PER_WHEEL = 0.0025;
// Gain applique au produit (pixels souris * SHIP.mouseSensitivity) pour obtenir
// une contribution utile sur un axe borne a [-1,1].
const MOUSE_GAIN = 24;

// code -> [nom d'axe, valeur cible]
//
// Schema volontairement minimal : quatre touches de pilotage et une de poussee.
// Sur un clavier AZERTY, KeyW est la touche "Z" et KeyA la touche "Q" : la table
// ci-dessous donne donc bien ZQSD, et fonctionne aussi en WASD sans changement.
const KEY_AXES = {
  // Z : descendre (nez vers le bas), S : monter (nez vers le haut).
  KeyW: ['pitch', -1],
  KeyS: ['pitch', 1],
  // Les fleches suivent l'intuition inverse : haut = monter.
  ArrowUp: ['pitch', 1],
  ArrowDown: ['pitch', -1],
  // Q et D tournent : c'est un virage (lacet), pas un tonneau.
  KeyA: ['yaw', 1],
  KeyD: ['yaw', -1],
  ArrowLeft: ['yaw', 1],
  ArrowRight: ['yaw', -1],
  // Roulis en second rideau, pour se remettre a plat ou faire le beau.
  KeyQ: ['roll', 1],
  KeyE: ['roll', -1],
  Space: ['thrust', 1],
};

// code -> nom de bouton
const KEY_BUTTONS = {
  ShiftLeft: 'boost',
  ShiftRight: 'boost',
  ControlLeft: 'brake',
  ControlRight: 'brake',
  KeyX: 'brake',
  KeyF: 'scan',
  KeyC: 'align',
  KeyJ: 'warp',
  KeyM: 'map',
  KeyV: 'cameraToggle',
  KeyL: 'land',
  KeyH: 'help',
  KeyG: 'gui',
};

// Touches dont on bloque l'action par defaut du navigateur (defilement).
// F5, F12, Ctrl+R, etc. ne sont jamais touches.
const PREVENT_DEFAULT = new Set([
  'Space',
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'PageUp',
  'PageDown',
  'Home',
  'End',
]);

// Boutons de manette -> noms de boutons logiques (disposition XInput standard).
const GAMEPAD_BUTTONS = {
  0: 'boost',
  1: 'brake',
  2: 'scan',
  3: 'cameraToggle',
  4: 'map',
  5: 'warp',
  8: 'help',
  9: 'gui',
};

const BUTTON_NAMES = [
  'boost',
  'brake',
  'scan',
  'align',
  'warp',
  'map',
  'cameraToggle',
  'land',
  'help',
  'gui',
];

const AXIS_NAMES = ['pitch', 'yaw', 'roll', 'thrust', 'strafe', 'vertical'];

/** Applique une zone morte et re-etale la course restante sur [0,1]. */
function applyDeadzone(v) {
  const a = Math.abs(v);
  if (a < DEADZONE) return 0;
  const scaled = (a - DEADZONE) / (1 - DEADZONE);
  return v < 0 ? -scaled : scaled;
}

/** Rampe lineaire independante du framerate. */
function approach(current, target, rate, dt) {
  const step = rate * dt;
  const d = target - current;
  if (d > step) return current + step;
  if (d < -step) return current - step;
  return target;
}

function isTypingTarget(t) {
  if (!t || !t.tagName) return false;
  const tag = t.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable === true;
}

export function createInput(domElement) {
  const element = domElement || (typeof document !== 'undefined' ? document.body : null);

  // Axes exposes (objet stable, jamais reconstruit).
  const axes = {
    pitch: 0,
    yaw: 0,
    roll: 0,
    thrust: 0,
    strafe: 0,
    vertical: 0,
    zoom: 0,
  };

  // Partie lissee provenant du clavier uniquement : la souris et la manette
  // s'ajoutent par-dessus sans ecraser le clavier.
  const smooth = { pitch: 0, yaw: 0, roll: 0, thrust: 0, strafe: 0, vertical: 0 };
  const target = { pitch: 0, yaw: 0, roll: 0, thrust: 0, strafe: 0, vertical: 0 };
  const analog = { pitch: 0, yaw: 0, roll: 0, thrust: 0, strafe: 0, vertical: 0 };

  const buttons = {};
  for (const name of BUTTON_NAMES) buttons[name] = false;

  const mouse = {
    dx: 0,
    dy: 0,
    wheel: 0,
    locked: false,
    // Masque de boutons de la souris : 1 = gauche, 2 = droit, 4 = milieu.
    buttons: 0,
  };

  const held = new Set(); // codes physiques enfonces
  let edgeCurrent = new Set(); // fronts lisibles pendant la frame courante
  let edgeNext = new Set(); // fronts accumules par les evenements

  let accDx = 0;
  let accDy = 0;
  let accWheel = 0;
  let wantLock = false;
  let gamepadIndex = -1;
  let gamepadConnected = false;
  const prevGamepadButtons = [];
  let disposed = false;

  // -------------------------------------------------------------------------
  // Ecouteurs
  // -------------------------------------------------------------------------

  function onKeyDown(e) {
    if (isTypingTarget(e.target)) return;
    const code = e.code;
    if (PREVENT_DEFAULT.has(code) && !e.metaKey && !e.altKey) e.preventDefault();
    if (!(code in KEY_AXES) && !(code in KEY_BUTTONS)) return;
    if (e.repeat || held.has(code)) return;
    held.add(code);
    edgeNext.add(code);
    const btn = KEY_BUTTONS[code];
    if (btn) edgeNext.add(btn);
  }

  function onKeyUp(e) {
    held.delete(e.code);
  }

  function onBlur() {
    held.clear();
    accDx = 0;
    accDy = 0;
    mouse.buttons = 0;
  }

  function onMouseMove(e) {
    // On ne prend le mouvement relatif que lorsqu'il est significatif :
    // pointerlock actif, ou bouton maintenu (visee par glissement).
    if (!mouse.locked && mouse.buttons === 0) return;
    accDx += e.movementX || 0;
    accDy += e.movementY || 0;
  }

  function onMouseDown(e) {
    mouse.buttons = e.buttons;
    edgeNext.add(`Mouse${e.button}`);
  }

  function onMouseUp(e) {
    mouse.buttons = e.buttons;
  }

  function onWheel(e) {
    if (isTypingTarget(e.target)) return;
    e.preventDefault();
    accWheel += e.deltaY || 0;
  }

  function onContextMenu(e) {
    e.preventDefault();
  }

  function onPointerLockChange() {
    mouse.locked = document.pointerLockElement === element;
    if (!mouse.locked) wantLock = false;
  }

  function onPointerLockError() {
    mouse.locked = false;
    wantLock = false;
  }

  function onGamepadConnected(e) {
    gamepadIndex = e.gamepad ? e.gamepad.index : 0;
    gamepadConnected = true;
  }

  function onGamepadDisconnected(e) {
    if (!e.gamepad || e.gamepad.index === gamepadIndex) {
      gamepadIndex = -1;
      gamepadConnected = false;
      prevGamepadButtons.length = 0;
    }
  }

  window.addEventListener('keydown', onKeyDown, { passive: false });
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('blur', onBlur);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
  window.addEventListener('gamepadconnected', onGamepadConnected);
  window.addEventListener('gamepaddisconnected', onGamepadDisconnected);
  document.addEventListener('pointerlockchange', onPointerLockChange);
  document.addEventListener('pointerlockerror', onPointerLockError);
  if (element) {
    element.addEventListener('mousedown', onMouseDown);
    element.addEventListener('wheel', onWheel, { passive: false });
    element.addEventListener('contextmenu', onContextMenu);
  }

  // -------------------------------------------------------------------------
  // Manette
  // -------------------------------------------------------------------------

  function pollGamepad() {
    for (const k of AXIS_NAMES) analog[k] = 0;
    if (typeof navigator === 'undefined' || !navigator.getGamepads) return;
    let pads;
    try {
      pads = navigator.getGamepads();
    } catch (err) {
      return;
    }
    if (!pads) return;
    let pad = gamepadIndex >= 0 ? pads[gamepadIndex] : null;
    if (!pad || !pad.connected) {
      pad = null;
      for (let i = 0; i < pads.length; i++) {
        if (pads[i] && pads[i].connected) {
          pad = pads[i];
          gamepadIndex = i;
          break;
        }
      }
    }
    gamepadConnected = !!pad;
    if (!pad) {
      prevGamepadButtons.length = 0;
      return;
    }

    const ga = pad.axes || [];
    // Stick gauche : X = virage (lacet, gauche = positif), Y = monter/descendre.
    // Meme logique que le clavier : on tourne, on ne fait pas de tonneau.
    analog.yaw = -applyDeadzone(ga[0] || 0);
    analog.pitch = -applyDeadzone(ga[1] || 0);
    // Stick droit : X = roulis, pour se remettre a plat.
    analog.roll = -applyDeadzone(ga[2] || 0);

    const gb = pad.buttons || [];
    const rt = gb[7] ? gb[7].value || (gb[7].pressed ? 1 : 0) : 0;
    const lt = gb[6] ? gb[6].value || (gb[6].pressed ? 1 : 0) : 0;
    analog.thrust = applyDeadzone(rt);
    if (lt > 0.3) buttons.brake = true;

    for (let i = 0; i < gb.length; i++) {
      const pressedNow = !!(gb[i] && gb[i].pressed);
      const name = GAMEPAD_BUTTONS[i];
      if (name && pressedNow) buttons[name] = true;
      if (pressedNow && !prevGamepadButtons[i]) {
        edgeCurrent.add(`Pad${i}`);
        if (name) edgeCurrent.add(name);
      }
      prevGamepadButtons[i] = pressedNow;
    }
  }

  // -------------------------------------------------------------------------
  // Mise a jour
  // -------------------------------------------------------------------------

  function update(dt) {
    if (disposed) return;
    const step = dt > 0 ? dt : 0;

    // Rotation des fronts : ce qui a ete collecte devient lisible maintenant.
    const swap = edgeCurrent;
    edgeCurrent = edgeNext;
    edgeNext = swap;
    edgeNext.clear();

    // Snapshot du mouvement souris accumule (lisible toute la frame).
    mouse.dx = accDx;
    mouse.dy = accDy;
    mouse.wheel = accWheel;
    accDx = 0;
    accDy = 0;
    accWheel = 0;

    // Boutons : recalcules a chaque frame, donc jamais bloques.
    for (const name of BUTTON_NAMES) buttons[name] = false;
    for (const code of held) {
      const btn = KEY_BUTTONS[code];
      if (btn) buttons[btn] = true;
    }

    // Cibles clavier.
    for (const k of AXIS_NAMES) target[k] = 0;
    for (const code of held) {
      const entry = KEY_AXES[code];
      if (entry) target[entry[0]] = clamp(target[entry[0]] + entry[1], -1, 1);
    }

    pollGamepad();

    for (const k of AXIS_NAMES) {
      smooth[k] = approach(smooth[k], target[k], AXIS_RAMP, step);
    }

    // Souris : s'ajoute au tangage et au lacet sans ecraser le clavier.
    const sens = SHIP.mouseSensitivity;
    const mousePitch = -mouse.dy * sens * MOUSE_GAIN;
    const mouseYaw = -mouse.dx * sens * MOUSE_GAIN;

    axes.pitch = clamp(smooth.pitch + analog.pitch + mousePitch, -1, 1);
    axes.yaw = clamp(smooth.yaw + analog.yaw + mouseYaw, -1, 1);
    axes.roll = clamp(smooth.roll + analog.roll, -1, 1);
    axes.thrust = clamp(smooth.thrust + analog.thrust, -1, 1);
    axes.strafe = clamp(smooth.strafe + analog.strafe, -1, 1);
    axes.vertical = clamp(smooth.vertical + analog.vertical, -1, 1);

    // Zoom molette : impulsion puis retour amorti vers zero.
    let zoom = clamp(api.zoom - mouse.wheel * ZOOM_PER_WHEEL, -1, 1);
    zoom = damp(zoom, 0, ZOOM_DAMP, step);
    if (Math.abs(zoom) < 1e-4) zoom = 0;
    api.zoom = zoom;
    axes.zoom = zoom;
  }

  const api = {
    axes,
    buttons,
    mouse,
    zoom: 0,

    get gamepadConnected() {
      return gamepadConnected;
    },

    /** Vrai une seule fois par appui : le front est consomme. */
    pressed(name) {
      if (edgeCurrent.delete(name)) return true;
      return false;
    },

    /** Etat brut d'une touche physique (code DOM). */
    isDown(code) {
      return held.has(code);
    },

    setLocked(value) {
      if (!element) return;
      if (value) {
        if (mouse.locked || wantLock) return;
        wantLock = true;
        try {
          const p = element.requestPointerLock ? element.requestPointerLock() : null;
          if (p && typeof p.catch === 'function') {
            p.catch(() => {
              wantLock = false;
            });
          }
        } catch (err) {
          wantLock = false;
        }
      } else {
        wantLock = false;
        try {
          if (document.pointerLockElement === element) document.exitPointerLock();
        } catch (err) {
          /* rien : le navigateur peut refuser */
        }
      }
    },

    update,

    dispose() {
      if (disposed) return;
      disposed = true;
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('gamepadconnected', onGamepadConnected);
      window.removeEventListener('gamepaddisconnected', onGamepadDisconnected);
      document.removeEventListener('pointerlockchange', onPointerLockChange);
      document.removeEventListener('pointerlockerror', onPointerLockError);
      if (element) {
        element.removeEventListener('mousedown', onMouseDown);
        element.removeEventListener('wheel', onWheel);
        element.removeEventListener('contextmenu', onContextMenu);
      }
      held.clear();
      edgeCurrent.clear();
      edgeNext.clear();
      api.setLocked(false);
    },
  };

  return api;
}
