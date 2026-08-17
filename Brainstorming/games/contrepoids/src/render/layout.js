/**
 * CONTREPOIDS - shared world-space layout constants.
 *
 * Every render module positions columns from the same three numbers, so a
 * platform, its rope and the player standing on it never drift apart.
 */

export const SPACING = 2.4; // metres between two grid-adjacent column centres
export const CRAN_UNIT = 0.5; // metres per height cran
export const PLATFORM_SIZE = 1.9; // plan footprint of a platform/ground tile
export const PLATFORM_THICK = 0.34; // half-thickness is not needed elsewhere
export const RIG_MARGIN = 1.1; // metres above the highest reachable cran for a pulley bar

export function worldX(gx) {
  return gx * SPACING;
}

export function worldZ(gz) {
  return gz * SPACING;
}

/** Y of the platform's top surface for a given height-in-crans value. */
export function worldY(h) {
  return h * CRAN_UNIT;
}
