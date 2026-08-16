/**
 * Console ARCADE.
 *
 * Deux vues dans un seul document: la galerie et la scene. La scene ne contient
 * jamais plus d'une iframe, et c'est la tout le contrat "un seul jeu a la fois":
 * demonter l'iframe detruit la boucle rAF du jeu, son contexte WebGL, son
 * AudioContext et ses ecouteurs, sans que le jeu ait quoi que ce soit a faire.
 *
 * Console et jeux partagent l'origine, donc on peut greffer un raccourci de
 * sortie dans le document du jeu sans modifier son code.
 */

const grid = document.getElementById('grid');
const empty = document.getElementById('empty');
const summary = document.getElementById('summary');
const search = document.getElementById('search');
const stage = document.getElementById('stage');
const stagebar = document.getElementById('stagebar');
const slot = document.getElementById('frame-slot');
const playing = document.getElementById('playing');
const loading = document.getElementById('loading');

let games = [];
let visible = [];
let cursor = 0;
let currentId = null;
let barTimer = 0;
let lastSignature = '';

// --------------------------------------------------------------------------
// donnees
// --------------------------------------------------------------------------

async function loadGames() {
  try {
    const response = await fetch('/api/games', { cache: 'no-store' });
    const data = await response.json();
    games = data.games || [];
  } catch {
    games = [];
  }
  applyFilter();
  route();
}

function applyFilter() {
  const needle = search.value.trim().toLowerCase();
  visible = needle
    ? games.filter((g) => (g.name + ' ' + g.description).toLowerCase().includes(needle))
    : games.slice();
  cursor = Math.min(cursor, Math.max(0, visible.length - 1));
  renderGallery();
}

// --------------------------------------------------------------------------
// galerie
// --------------------------------------------------------------------------

/** Deux ou trois lettres tirees du nom: la vignette est generee, pas chargee. */
function monogram(name) {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, ' ').split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function renderGallery(force = false) {
  // le rescan tourne toutes les 5 s: sans cette garde on reconstruirait la
  // grille en boucle, ce qui casserait le focus clavier en cours
  const signature = cursor + '|' + visible.map((g) => `${g.id}:${g.ready}:${g.stale}`).join(',');
  if (!force && signature === lastSignature) return;
  lastSignature = signature;

  grid.textContent = '';
  empty.hidden = games.length > 0;

  visible.forEach((game, index) => {
    const card = document.createElement('article');
    card.className = 'card';
    card.dataset.id = game.id;
    card.style.setProperty('--h', String(game.accent));
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    if (!game.ready) card.classList.add('card-blocked');
    if (index === cursor) card.classList.add('is-cursor');

    const art = document.createElement('div');
    art.className = 'card-art';
    art.setAttribute('aria-hidden', 'true');
    art.dataset.mono = monogram(game.name);
    card.appendChild(art);

    const body = document.createElement('div');
    body.className = 'card-body';

    const title = document.createElement('h2');
    title.className = 'card-title';
    title.textContent = game.name;
    body.appendChild(title);

    const desc = document.createElement('p');
    desc.className = 'card-desc';
    desc.textContent = game.description || 'Pas de description.';
    body.appendChild(desc);

    const meta = document.createElement('p');
    meta.className = 'card-meta';
    if (!game.ready) {
      meta.classList.add('warn');
      meta.textContent = 'A construire : ' + game.buildHint;
    } else if (game.stale) {
      meta.classList.add('warn');
      meta.textContent = 'dist/ plus ancien que src/ : relancer le build pour voir les dernieres modifs.';
    } else {
      meta.textContent = `/g/${game.id}/  ·  ${game.built ? 'build dist/' : 'fichiers du dossier'}`;
    }
    body.appendChild(meta);

    card.appendChild(body);

    card.addEventListener('click', () => play(game.id));
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        play(game.id);
      }
    });
    grid.appendChild(card);
  });

  const ready = games.filter((g) => g.ready).length;
  summary.textContent = games.length
    ? `${games.length} jeu${games.length > 1 ? 'x' : ''} · ${ready} pret${ready > 1 ? 's' : ''}`
    : '';
}

function moveCursor(delta) {
  if (!visible.length) return;
  cursor = (cursor + delta + visible.length) % visible.length;
  renderGallery();
  const card = grid.children[cursor];
  if (card) {
    card.focus({ preventScroll: true });
    card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

// --------------------------------------------------------------------------
// scene
// --------------------------------------------------------------------------

function mount(game) {
  unmount();
  currentId = game.id;

  const frame = document.createElement('iframe');
  frame.className = 'frame';
  frame.title = game.name;
  // Pas de 'pointer-lock' ici: ce n'est pas une feature de Permissions-Policy
  // reconnue (Chrome la rejette avec un avertissement), et une iframe de meme
  // origine obtient le verrouillage du pointeur sans delegation. Pas de
  // allowfullscreen non plus: allow="fullscreen" le remplace et prend le pas.
  frame.allow = 'fullscreen; gamepad; autoplay; xr-spatial-tracking; accelerometer; gyroscope';
  frame.src = game.url;

  loading.hidden = false;
  frame.addEventListener('load', () => {
    loading.hidden = true;
    hookFrame(frame);
    try {
      frame.contentWindow.focus();
    } catch {
      /* jamais en pratique: meme origine */
    }
  });

  slot.appendChild(frame);
  playing.textContent = game.name;
  document.body.dataset.view = 'stage';
  stage.hidden = false;
  revealBar(4000);
}

function unmount() {
  const frame = slot.querySelector('iframe');
  if (frame) {
    // about:blank avant le retrait: le navigateur decharge le document tout de
    // suite au lieu d'attendre le ramassage de l'iframe detachee
    try {
      frame.contentWindow.location.replace('about:blank');
    } catch {
      /* ignore */
    }
    frame.remove();
  }
  if (document.pointerLockElement) document.exitPointerLock();
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  currentId = null;
  loading.hidden = true;
}

/**
 * Greffe le raccourci de sortie dans le document du jeu. Possible uniquement
 * parce que console et jeu partagent l'origine. En capture, pour passer avant
 * les ecouteurs du jeu.
 */
function hookFrame(frame) {
  let doc;
  try {
    doc = frame.contentDocument;
  } catch {
    return;
  }
  if (!doc) return;
  doc.addEventListener('keydown', onExitKey, true);
  // le pointer lock qui se relache veut presque toujours dire "le joueur veut
  // reprendre la main": on montre la barre sans qu'il ait a la chercher
  doc.addEventListener('pointerlockchange', () => {
    if (!doc.pointerLockElement) revealBar(3000);
  });
  doc.addEventListener('mousemove', (event) => {
    if (event.clientY <= 56) revealBar(2000);
  });
}

/**
 * F2 marche en toutes circonstances. Maj+Echap est le raccourci naturel mais le
 * navigateur avale Echap tant que le pointeur est verrouille, donc il ne sert
 * qu'une fois le pointeur relache.
 */
function onExitKey(event) {
  if (event.key === 'F2' || (event.key === 'Escape' && event.shiftKey)) {
    event.preventDefault();
    event.stopPropagation();
    goHome();
  }
}

function revealBar(duration) {
  stagebar.classList.add('is-visible');
  clearTimeout(barTimer);
  barTimer = setTimeout(() => stagebar.classList.remove('is-visible'), duration);
}

// --------------------------------------------------------------------------
// routage
// --------------------------------------------------------------------------

function play(id) {
  const game = games.find((g) => g.id === id);
  if (!game || !game.ready) return;
  const path = `/play/${encodeURIComponent(id)}`;
  // l'historique reste [galerie, jeu courant]: passer d'un jeu a l'autre
  // remplace l'entree au lieu d'en empiler une, sinon "Console" et le bouton
  // Precedent ramenent au jeu d'avant au lieu de la galerie
  if (currentId) history.replaceState({ arcade: true }, '', path);
  else history.pushState({ arcade: true }, '', path);
  route();
}

function goHome() {
  // si c'est nous qui avons empile l'entree, on la depile pour que l'historique
  // du navigateur reste coherent avec le bouton Precedent
  if (history.state && history.state.arcade) history.back();
  else {
    history.pushState({}, '', '/');
    route();
  }
}

function route() {
  const match = location.pathname.match(/^\/play\/(.+)$/);
  const id = match ? decodeURIComponent(match[1]) : null;

  if (!id) {
    if (currentId) unmount();
    stage.hidden = true;
    document.body.dataset.view = 'gallery';
    return;
  }
  const game = games.find((g) => g.id === id);
  if (!game || !game.ready) {
    history.replaceState({}, '', '/');
    route();
    return;
  }
  if (currentId !== id) mount(game);
}

// --------------------------------------------------------------------------
// evenements
// --------------------------------------------------------------------------

window.addEventListener('popstate', route);

document.getElementById('back').addEventListener('click', goHome);
document.getElementById('reload').addEventListener('click', () => {
  const game = games.find((g) => g.id === currentId);
  if (game) mount(game);
});
document.getElementById('fullscreen').addEventListener('click', () => {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else stage.requestFullscreen().catch(() => {});
});

stage.addEventListener('mousemove', (event) => {
  if (event.clientY <= 56) revealBar(2000);
});

search.addEventListener('input', applyFilter);

document.addEventListener('keydown', (event) => {
  if (document.body.dataset.view === 'stage') {
    onExitKey(event);
    return;
  }
  if (event.target === search) {
    if (event.key === 'Escape') {
      search.value = '';
      applyFilter();
      search.blur();
    }
    if (event.key === 'Enter' && visible.length) play(visible[cursor].id);
    return;
  }
  if (event.key === '/') {
    event.preventDefault();
    search.focus();
    return;
  }
  if (event.key === 'ArrowRight') moveCursor(1);
  else if (event.key === 'ArrowLeft') moveCursor(-1);
  else if (event.key === 'Enter' && visible.length) play(visible[cursor].id);
});

// un rescan cote serveur suffit a faire apparaitre un jeu ajoute ou construit
// pendant la session, mais on ne rafraichit pas la galerie pendant une partie
setInterval(() => {
  if (document.body.dataset.view === 'gallery' && !document.hidden) loadGames();
}, 5000);

loadGames();
