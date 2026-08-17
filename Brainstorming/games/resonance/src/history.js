/**
 * RESONANCE - unlimited undo stack.
 *
 * Entries are plain objects built by main.js ({type, ...payload, step}); this
 * module only owns the stack discipline. Redo is intentionally absent: the
 * simulation is live, replaying forward would surprise more than it helps.
 */

export function createHistory() {
  const stack = [];

  function push(entry) { stack.push(entry); }

  function undo() { return stack.length ? stack.pop() : null; }

  function clear() { stack.length = 0; }

  return { push, undo, clear, get length() { return stack.length; } };
}
