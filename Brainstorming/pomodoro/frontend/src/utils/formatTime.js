/**
 * Time formatting utilities — monospace-friendly, zero-padded.
 */

/**
 * Format seconds into MM:SS
 */
export const formatTime = (totalSeconds) => {
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

/**
 * Format seconds into H:MM:SS for longer durations
 */
export const formatTimeLong = (totalSeconds) => {
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return formatTime(totalSeconds);
};

/**
 * Format minutes into human-readable string
 */
export const formatMinutes = (minutes) => {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
};

/**
 * Calculate level from XP: Level = floor(sqrt(totalXP / 10))
 */
export const calculateLevel = (xp) => {
  return Math.floor(Math.sqrt(xp / 10));
};

/**
 * XP needed for a given level
 */
export const xpForLevel = (level) => {
  return level * level * 10;
};

/**
 * Progress within current level (0-1)
 */
export const levelProgress = (xp) => {
  const currentLevel = calculateLevel(xp);
  const currentLevelXp = xpForLevel(currentLevel);
  const nextLevelXp = xpForLevel(currentLevel + 1);
  return (xp - currentLevelXp) / (nextLevelXp - currentLevelXp);
};

/**
 * Format date to YYYY-MM-DD
 */
export const formatDate = (date) => {
  const d = new Date(date);
  return d.toISOString().split('T')[0];
};

export default {
  formatTime,
  formatTimeLong,
  formatMinutes,
  calculateLevel,
  xpForLevel,
  levelProgress,
  formatDate,
};
