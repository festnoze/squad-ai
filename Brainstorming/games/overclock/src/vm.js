/**
 * OVERCLOCK - interpreter.
 *
 * Pure: it only knows about a program and a warehouse. One call to step()
 * consumes exactly one slot and returns one event, which is what lets the
 * renderer animate the machine at any speed, including one step at a time.
 *
 * A call with nothing left to come back to replaces its frame instead of
 * pushing one (tail call). Without it a recursive procedure used as a loop
 * would blow the stack after a couple of hundred iterations, and "boucle
 * infinie" would be reported for programs that are simply long running.
 * "Nothing left" means trailing empty slots too: a player who leaves the last
 * slot of a procedure blank has not written a different program.
 */

import { OPS } from './program.js';

export const MAX_STEPS = 5000;
export const MAX_DEPTH = 200;

export function createVM(warehouse, program, opts) {
  const maxSteps = (opts && opts.maxSteps) || MAX_STEPS;
  const maxDepth = (opts && opts.maxDepth) || MAX_DEPTH;

  /** True when slots [from, end) of a procedure hold nothing executable. */
  function restEmpty(procIndex, from) {
    const slots = program.procs[procIndex].slots;
    for (let i = from; i < slots.length; i++) if (slots[i]) return false;
    return true;
  }

  const vm = {
    warehouse,
    program,
    stack: [],
    steps: 0,
    status: 'running', // running | win | halt | limit | overflow

    reset() {
      vm.stack.length = 0;
      vm.stack.push({ proc: 0, pc: 0 });
      vm.steps = 0;
      vm.status = 'running';
      return vm;
    },

    get depth() {
      return vm.stack.length;
    },

    /** Slot that step() will consume next, or null when nothing is left. */
    peek() {
      for (let i = vm.stack.length - 1; i >= 0; i--) {
        const f = vm.stack[i];
        if (!restEmpty(f.proc, f.pc)) return { proc: f.proc, slot: f.pc };
      }
      return null;
    },

    step() {
      if (vm.status !== 'running') return { kind: 'end', status: vm.status, proc: -1, slot: -1 };

      // Unwind exhausted frames. Returning costs no step: it is bookkeeping.
      while (vm.stack.length) {
        const f = vm.stack[vm.stack.length - 1];
        if (restEmpty(f.proc, f.pc)) vm.stack.pop();
        else break;
      }
      if (!vm.stack.length) {
        vm.status = 'halt';
        return { kind: 'end', status: 'halt', proc: -1, slot: -1 };
      }
      if (vm.steps >= maxSteps) {
        vm.status = 'limit';
        const at = vm.peek();
        return { kind: 'end', status: 'limit', proc: at ? at.proc : -1, slot: at ? at.slot : -1 };
      }

      const frame = vm.stack[vm.stack.length - 1];
      const procIndex = frame.proc;
      const slotIndex = frame.pc;
      const inst = program.procs[procIndex].slots[slotIndex];
      frame.pc++;
      vm.steps++;

      const ev = {
        kind: 'run',
        proc: procIndex,
        slot: slotIndex,
        op: inst ? inst.op : null,
        cond: inst ? inst.cond : null,
        ok: true,
        reason: '',
        detail: null,
        status: 'running',
      };

      if (!inst) {
        ev.kind = 'empty';
        return ev;
      }

      if (inst.cond && warehouse.colorUnder() !== inst.cond) {
        ev.kind = 'skip';
        ev.reason = 'CONDITION NON REMPLIE';
        return ev;
      }

      const def = OPS[inst.op];
      if (!def) {
        ev.kind = 'empty';
        return ev;
      }

      if (def.call !== undefined) {
        ev.kind = 'call';
        ev.target = def.call;
        if (!program.procs[def.call]) {
          ev.ok = false;
          ev.reason = 'PROCEDURE ABSENTE';
          return ev;
        }
        // Tail call: nothing left to come back to, so reuse the frame.
        if (restEmpty(procIndex, frame.pc)) vm.stack.pop();
        if (vm.stack.length >= maxDepth) {
          vm.status = 'overflow';
          ev.ok = false;
          ev.status = 'overflow';
          ev.reason = 'PILE D APPELS SATUREE (' + maxDepth + ')';
          return ev;
        }
        vm.stack.push({ proc: def.call, pc: 0 });
        return ev;
      }

      let res;
      switch (inst.op) {
        case 'FWD': res = warehouse.forward(); break;
        case 'LEFT': res = warehouse.turn(-1); break;
        case 'RIGHT': res = warehouse.turn(1); break;
        case 'JUMP': res = warehouse.jump(); break;
        case 'ACT': res = warehouse.activate(); break;
        case 'GRAB': res = warehouse.grab(); break;
        case 'DROP': res = warehouse.drop(); break;
        case 'PAINT_R': res = warehouse.paint('r'); break;
        case 'PAINT_G': res = warehouse.paint('g'); break;
        case 'PAINT_B': res = warehouse.paint('b'); break;
        default: res = { ok: false, reason: 'INSTRUCTION INCONNUE' }; break;
      }

      ev.ok = res.ok;
      ev.reason = res.reason;
      ev.detail = res;

      if (warehouse.solved()) {
        vm.status = 'win';
        ev.status = 'win';
      }
      return ev;
    },
  };

  return vm.reset();
}

export const STATUS_LABEL = {
  running: 'EN COURS',
  win: 'TOUTES LES CIBLES ALLUMEES',
  halt: 'PROGRAMME TERMINE, CIBLES RESTANTES',
  limit: 'BOUCLE INFINIE DETECTEE (' + MAX_STEPS + ' PAS)',
  overflow: 'PILE D APPELS SATUREE (' + MAX_DEPTH + ')',
};
