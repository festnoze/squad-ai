// UI du launcher: liste les jeux, demande le demarrage, ouvre l'onglet quand le port repond.

const grid = document.getElementById('grid');
const empty = document.getElementById('empty');
const summary = document.getElementById('summary');
const logsDialog = document.getElementById('logs');
const logsTitle = document.getElementById('logs-title');
const logsBody = document.getElementById('logs-body');

const STATE_LABEL = {
  stopped: 'a l arret',
  installing: 'installation des dependances',
  starting: 'demarrage',
  running: 'en cours',
  external: 'deja en ligne',
  error: 'erreur',
};

// onglets ouverts en attente du port, par identifiant de jeu
const pendingTabs = new Map();
let games = [];

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function initials(name) {
  return name.split(/\s+/).slice(0, 2).map((word) => word[0] || '').join('').toUpperCase();
}

function cardFor(game) {
  const card = document.createElement('article');
  card.className = 'card';
  card.dataset.id = game.id;

  const cover = document.createElement('div');
  cover.className = 'cover';
  if (game.hasCover) {
    cover.style.backgroundImage = `url(/api/cover?id=${encodeURIComponent(game.id)})`;
  } else {
    cover.textContent = initials(game.name);
  }

  const body = document.createElement('div');
  body.className = 'card-body';
  body.innerHTML = `
    <div class="card-head">
      <h2></h2>
      <span class="port"></span>
    </div>
    <p class="desc"></p>
    <div class="state"><span class="dot"></span><span class="state-label"></span></div>
    <div class="meta"></div>
    <div class="actions">
      <button class="primary" type="button" data-action="play">Jouer</button>
      <button class="ghost" type="button" data-action="stop">Arreter</button>
      <button class="ghost" type="button" data-action="logs">Journal</button>
    </div>`;

  body.querySelector('h2').textContent = game.name;
  body.querySelector('.desc').textContent = game.description || 'Pas de description dans le README.';
  card.append(cover, body);

  body.querySelector('[data-action="play"]').addEventListener('click', () => play(game.id));
  body.querySelector('[data-action="stop"]').addEventListener('click', () => stop(game.id));
  body.querySelector('[data-action="logs"]').addEventListener('click', () => showLogs(game.id));
  return card;
}

function paint(game) {
  let card = grid.querySelector(`.card[data-id="${CSS.escape(game.id)}"]`);
  if (!card) {
    card = cardFor(game);
    grid.append(card);
  }
  const stateRow = card.querySelector('.state');
  stateRow.className = `state state-${game.state}`;
  stateRow.querySelector('.state-label').textContent =
    game.detail ? `${STATE_LABEL[game.state]} - ${game.detail}` : STATE_LABEL[game.state];

  card.querySelector('.port').textContent = `port ${game.port}${game.portDetected ? '' : ' (par defaut)'}`;
  card.querySelector('.meta').textContent = `${game.folder} - ${game.command}`;

  const busy = game.state === 'starting' || game.state === 'installing';
  const play = card.querySelector('[data-action="play"]');
  play.disabled = busy;
  play.textContent = busy ? 'Demarrage...' : (game.state === 'running' || game.state === 'external' ? 'Ouvrir' : 'Jouer');
  card.querySelector('[data-action="stop"]').disabled = game.state !== 'running' && !busy;
}

function reconcile(fresh) {
  games = fresh;
  const ids = new Set(fresh.map((game) => game.id));
  grid.querySelectorAll('.card').forEach((card) => {
    if (!ids.has(card.dataset.id)) card.remove();
  });
  fresh.forEach(paint);

  empty.hidden = fresh.length > 0;
  const live = fresh.filter((game) => game.state === 'running' || game.state === 'external').length;
  summary.textContent = `${fresh.length} jeu${fresh.length > 1 ? 'x' : ''} detecte${fresh.length > 1 ? 's' : ''}, ${live} en ligne`;

  // un onglet en attente recoit son URL des que le serveur repond
  fresh.forEach((game) => {
    const tab = pendingTabs.get(game.id);
    if (!tab) return;
    if (game.state === 'running' || game.state === 'external') {
      pendingTabs.delete(game.id);
      try {
        tab.location.replace(game.url);
      } catch {
        window.open(game.url, '_blank');
      }
    } else if (game.state === 'error') {
      pendingTabs.delete(game.id);
      try { tab.close(); } catch { /* onglet deja ferme par l utilisateur */ }
      showLogs(game.id);
    }
  });
}

async function refresh() {
  try {
    const payload = await api('/api/games');
    reconcile(payload.games);
  } catch (error) {
    summary.textContent = `launcher injoignable: ${error.message}`;
  }
}

async function play(id) {
  const game = games.find((entry) => entry.id === id);
  if (!game) return;

  // l onglet doit etre ouvert pendant le clic, sinon le navigateur le bloque
  if (game.state === 'running' || game.state === 'external') {
    window.open(game.url, '_blank');
    return;
  }
  const tab = window.open('', '_blank');
  if (tab) {
    tab.document.write(
      `<title>${game.name}</title><body style="background:#07090f;color:#8a97b1;font-family:system-ui;padding:40px">` +
      `Demarrage de ${game.name} sur le port ${game.port}...</body>`);
    pendingTabs.set(id, tab);
  }
  try {
    const result = await api('/api/launch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    reconcile(games.map((entry) => (entry.id === id ? { ...entry, ...result } : entry)));
  } catch (error) {
    pendingTabs.delete(id);
    if (tab) tab.close();
    summary.textContent = `echec du lancement: ${error.message}`;
  }
  refresh();
}

async function stop(id) {
  pendingTabs.delete(id);
  try {
    await api('/api/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
  } catch (error) {
    summary.textContent = `echec de l arret: ${error.message}`;
  }
  refresh();
}

async function showLogs(id) {
  const game = games.find((entry) => entry.id === id);
  logsTitle.textContent = `Journal - ${game ? game.name : id}`;
  try {
    const payload = await api(`/api/logs?id=${encodeURIComponent(id)}`);
    logsBody.textContent = payload.lines.length ? payload.lines.join('\n') : 'Rien a afficher pour le moment.';
  } catch (error) {
    logsBody.textContent = error.message;
  }
  if (!logsDialog.open) logsDialog.showModal();
  logsBody.scrollTop = logsBody.scrollHeight;
}

document.getElementById('refresh').addEventListener('click', refresh);
document.getElementById('logs-close').addEventListener('click', () => logsDialog.close());

refresh();
setInterval(refresh, 2000);
