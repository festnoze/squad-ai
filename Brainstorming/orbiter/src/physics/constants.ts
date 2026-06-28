/**
 * Physical constants and reference data (SI units: metres, seconds, kilograms).
 *
 * Gravitational parameters μ = G·M are quoted directly (they are known far more
 * precisely than G or the masses separately). Sources: IAU / JPL standard values.
 */

export const G = 6.6743e-11; // m^3 kg^-1 s^-2 (CODATA)

export const AU = 1.495978707e11; // m — astronomical unit
export const DEG = Math.PI / 180;
export const DAY = 86400; // s (mean solar day)

/** Standard gravitational parameters μ = G·M  [m^3/s^2]. */
export const MU = {
  sun: 1.32712440018e20,
  earth: 3.986004418e14,
  moon: 4.9028695e12,
  mars: 4.282837e13,
} as const;

/** Masses [kg] (derived from μ/G), used for mass ratios (Lagrange points). */
export const MASS = {
  sun: MU.sun / G,
  earth: MU.earth / G,
  moon: MU.moon / G,
  mars: MU.mars / G,
} as const;

/** Mean equatorial radii [m]. */
export const RADIUS = {
  sun: 6.957e8,
  earth: 6.371e6,
  moon: 1.7374e6,
  mars: 3.3895e6,
} as const;

/** Sidereal rotation periods [s] (for stationary orbits). The Moon is tidally
 * locked, so its sidereal rotation equals the sidereal month. */
export const SIDEREAL_ROTATION = {
  earth: 86164.0905, // sidereal day
  moon: 27.321661 * DAY, // synchronous with its sidereal orbital period
} as const;

/** Mean Earth–Moon distance [m] and the sidereal month [s]. */
export const EARTH_MOON_DISTANCE = 3.84399e8;
export const SIDEREAL_MONTH = 27.321661 * DAY;

/** J2000.0 epoch as a Unix timestamp [ms] — 2000-01-01T12:00:00 TT (≈UTC here). */
export const J2000_UNIX_MS = Date.UTC(2000, 0, 1, 12, 0, 0);

/** Seconds elapsed since the J2000 epoch for a given Unix time [ms]. */
export function secondsSinceJ2000(unixMs: number): number {
  return (unixMs - J2000_UNIX_MS) / 1000;
}

/** Julian centuries since J2000 (used by the planetary element rates). */
export function centuriesSinceJ2000(unixMs: number): number {
  return secondsSinceJ2000(unixMs) / (DAY * 36525);
}
