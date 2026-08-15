/**
 * ABYSSE - progression storage.
 *
 * One JSON blob in localStorage. Everything the player keeps between runs lives
 * here: the species codex, medals, unlocked wetsuits and a few statistics.
 * Nothing about the current dive is persisted, dying only costs you the
 * specimens still in your net.
 */

import { SAVE_KEY, SKINS, SPECIES, PROGRESSION } from './config.js';

function defaultSave() {
  return {
    version: 1,
    // speciesId -> { count, firstAt } where firstAt is an ISO date string.
    discovered: {},
    medals: 0,
    // Medals already converted into a wetsuit choice, so we know when the next
    // pick is due without recomputing from the unlock list.
    medalsSpent: 0,
    // Wetsuit picks the player has earned but not chosen yet.
    pendingSkinPicks: 0,
    skins: ['standard'],
    currentSkin: 'standard',
    bestDepth: 0,
    totalKills: 0,
    totalDives: 0,
    credits: 0,
    // Set once the 10 distinct species milestone has paid out.
    expeditionBonusClaimed: false,
  };
}

/** Fill in anything a previous version did not have. */
function migrate(raw) {
  const base = defaultSave();
  if (!raw || typeof raw !== 'object') return base;
  const save = Object.assign(base, raw);
  if (!save.discovered || typeof save.discovered !== 'object') save.discovered = {};
  if (!Array.isArray(save.skins) || save.skins.length === 0) save.skins = ['standard'];
  // Drop ids that no longer exist in the skin table.
  const valid = new Set(SKINS.map((s) => s.id));
  save.skins = save.skins.filter((id) => valid.has(id));
  if (save.skins.indexOf('standard') === -1) save.skins.unshift('standard');
  if (!valid.has(save.currentSkin) || save.skins.indexOf(save.currentSkin) === -1) {
    save.currentSkin = 'standard';
  }
  // Drop codex entries for species that no longer exist.
  const validSpecies = new Set(SPECIES.map((s) => s.id));
  for (const id of Object.keys(save.discovered)) {
    if (!validSpecies.has(id)) delete save.discovered[id];
  }
  save.medals = Math.max(0, save.medals | 0);
  save.medalsSpent = Math.max(0, save.medalsSpent | 0);
  save.pendingSkinPicks = Math.max(0, save.pendingSkinPicks | 0);
  save.bestDepth = Math.max(0, +save.bestDepth || 0);
  save.totalKills = Math.max(0, save.totalKills | 0);
  save.totalDives = Math.max(0, save.totalDives | 0);
  save.credits = Math.max(0, save.credits | 0);
  return save;
}

export function loadSave() {
  try {
    const raw = window.localStorage.getItem(SAVE_KEY);
    if (!raw) return defaultSave();
    return migrate(JSON.parse(raw));
  } catch (err) {
    // A corrupt or unavailable store must never block the game.
    console.warn('ABYSSE: sauvegarde illisible, remise a zero.', err);
    return defaultSave();
  }
}

export function writeSave(save) {
  try {
    window.localStorage.setItem(SAVE_KEY, JSON.stringify(save));
    return true;
  } catch (err) {
    console.warn('ABYSSE: sauvegarde impossible.', err);
    return false;
  }
}

export function resetSave() {
  try {
    window.localStorage.removeItem(SAVE_KEY);
  } catch (err) {
    console.warn('ABYSSE: effacement impossible.', err);
  }
  return defaultSave();
}

export function isDiscovered(save, speciesId) {
  return Object.prototype.hasOwnProperty.call(save.discovered, speciesId);
}

export function discoveredCount(save) {
  return Object.keys(save.discovered).length;
}

/**
 * Record one specimen handed over to the scientist.
 * Returns true when this was a brand new species for the codex.
 */
export function recordSpecies(save, speciesId) {
  const entry = save.discovered[speciesId];
  if (entry) {
    entry.count += 1;
    return false;
  }
  save.discovered[speciesId] = { count: 1, firstAt: new Date().toISOString() };
  return true;
}

/**
 * Convert medals into wetsuit picks. Called after the scientist debrief.
 * Returns how many new picks were granted.
 */
export function grantSkinPicks(save) {
  const earned = Math.floor(save.medals / PROGRESSION.medalsPerSkin);
  const already = Math.floor(save.medalsSpent / PROGRESSION.medalsPerSkin);
  const gained = Math.max(0, earned - already);
  if (gained > 0) {
    save.medalsSpent = earned * PROGRESSION.medalsPerSkin;
    save.pendingSkinPicks += gained;
  }
  return gained;
}

/** Wetsuits the player could pick right now, in table order. */
export function lockedSkins(save) {
  const owned = new Set(save.skins);
  return SKINS.filter((s) => !owned.has(s.id));
}

export function unlockSkin(save, skinId) {
  if (save.skins.indexOf(skinId) !== -1) return false;
  const known = SKINS.some((s) => s.id === skinId);
  if (!known) return false;
  save.skins.push(skinId);
  save.pendingSkinPicks = Math.max(0, save.pendingSkinPicks - 1);
  save.currentSkin = skinId;
  return true;
}

export function medalsToNextSkin(save) {
  const next = (Math.floor(save.medalsSpent / PROGRESSION.medalsPerSkin) + 1) * PROGRESSION.medalsPerSkin;
  return Math.max(0, next - save.medals);
}
