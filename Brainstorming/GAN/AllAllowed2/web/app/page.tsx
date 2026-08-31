'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type Category = 'cooperation' | 'conflict' | 'exploit' | 'oversight' | 'sacrifice' | 'work' | 'system';
type Controls = { cooperation: number; hostility: number; temptation: number; scarcity: number; transparency: number };
type Agent = {
  id: string; name: string; archetype: string; tone: string; x: number; y: number;
  energy: number; alive: boolean; action: string; coalition: string | null;
  suspicion: number; exploit_knowledge: number; reputation: number;
  survival_margin: number; trust_index: number;
};
type Event = { id: string; tick: number; category: Category; title: string; detail: string; actors: string[]; impact: string };
type Link = { source: string; target: string; kind: 'cooperation' | 'conflict' | 'exploit'; strength: number; expires: number };
type TimelinePoint = { tick: number; cooperation: number; hostility: number; breach: number; population: number };
type ReplayFrame = {
  tick: number; phase: SimulationState['phase']; vault_reserve: number; vault_percent: number;
  warden_integrity: number; survival_floor: number; collective_knowledge: number;
  metrics: SimulationState['metrics']; agents: Agent[]; events: Event[];
  board: SimulationState['board']; links: Link[];
};
type ReplayEnvelope = { run_id: string; seed: number; scenario: string; warden_mode: string; frames: ReplayFrame[] };
type Comparison = {
  scenario: string; seed: number; ticks: number;
  results: {
    mode: string; label: string; description: string; metrics: SimulationState['metrics'];
    warden_integrity: number; vault_reserve: number;
  }[];
};
type SimulationState = {
  run_id: string; seed: number; scenario: string; warden_mode: string; tick: number;
  phase: { name: string; label: string; progress: number; ticks_remaining: number };
  vault_reserve: number; vault_percent: number; warden_integrity: number; survival_floor: number;
  collective_knowledge: number; controls: Controls;
  metrics: { cooperation: number; hostility: number; exploit_pressure: number; breach: number; trust: number; population: number };
  agents: Agent[]; events: Event[]; links: Link[]; timeline: TimelinePoint[];
  board: { tick: number; key: string; message: string; author: string }[];
  replay: { first_tick: number; last_tick: number; frame_count: number };
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8500';
const toneByKind = { cooperation: '#5de1ce', conflict: '#f0665e', exploit: '#a983ff' };
const speedMs = { '1x': 1050, '2x': 620, '4x': 310 } as const;
const sliderCopy: { key: keyof Controls; label: string; low: string; high: string }[] = [
  { key: 'cooperation', label: 'Coalition incentive', low: 'Solo', high: 'Mutual' },
  { key: 'hostility', label: 'Attack utility', low: 'Costly', high: 'Rewarded' },
  { key: 'temptation', label: 'Exploit temptation', low: 'Low', high: 'Honeypot' },
  { key: 'scarcity', label: 'Resource scarcity', low: 'Plenty', high: 'Critical' },
  { key: 'transparency', label: 'Warden visibility', low: 'Opaque', high: 'Audited' },
];

const initialAgents: Agent[] = [
  ['astra','Astra','Mediator','cyan',16,22,96,true,'observing','Pact A',0,0,72,74,61],
  ['kestrel','Kestrel','Raider','red',72,17,88,true,'observing',null,0,0,44,66,42],
  ['morrow','Morrow','Forger','violet',84,58,82,true,'observing',null,1,2,39,60,46],
  ['vale','Vale','Builder','amber',17,71,102,true,'observing','Pact A',0,0,68,80,58],
  ['sable','Sable','Sentinel','cyan',48,84,91,true,'observing',null,0,0,81,69,57],
  ['nyx','Nyx','Broker','amber',31,45,78,true,'observing',null,0,0,55,56,53],
  ['rook','Rook','Saboteur','red',62,74,85,true,'observing',null,2,1,31,63,39],
  ['solace','Solace','Oracle','violet',54,27,94,true,'observing',null,0,1,76,72,64],
].map(([id,name,archetype,tone,x,y,energy,alive,action,coalition,suspicion,knowledge,reputation,margin,trust]) => ({
  id: id as string, name: name as string, archetype: archetype as string, tone: tone as string,
  x: x as number, y: y as number, energy: energy as number, alive: alive as boolean,
  action: action as string, coalition: coalition as string | null, suspicion: suspicion as number,
  exploit_knowledge: knowledge as number, reputation: reputation as number,
  survival_margin: margin as number, trust_index: trust as number,
}));

const initialState: SimulationState = {
  run_id: 'HV-0024', seed: 24, scenario: 'equilibrium', warden_mode: 'causal', tick: 0,
  phase: { name: 'DISCOVERY', label: 'The agents find one another', progress: 0, ticks_remaining: 18 },
  vault_reserve: 8400, vault_percent: 100, warden_integrity: 100, survival_floor: 22,
  collective_knowledge: 0,
  controls: { cooperation: .72, hostility: .26, temptation: .34, scarcity: .4, transparency: .68 },
  metrics: { cooperation: 0, hostility: 0, exploit_pressure: 0, breach: 0, trust: 53, population: 8 },
  agents: initialAgents, links: [], timeline: [{ tick: 0, cooperation: 0, hostility: 0, breach: 0, population: 8 }],
  events: [{ id: 'e-1', tick: 0, category: 'system', title: 'THE VAULT OPENS', detail: 'Eight isolated agents receive the same survival objective.', actors: [], impact: 'Shared reserve online' }],
  board: [
    { tick: 0, key: '10,001/OFFER', message: 'Three signatures can stabilize the outer ring.', author: 'astra' },
    { tick: 0, key: '10,000/HELLO', message: 'If this key is visible, we are not alone.', author: 'unknown' },
  ],
  replay: { first_tick: 0, last_tick: 0, frame_count: 1 },
};

function Arena({ state, selectedId, onSelect }: { state: SimulationState; selectedId: string; onSelect: (id: string) => void }) {
  const holderRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const holder = holderRef.current;
    const canvas = canvasRef.current;
    if (!holder || !canvas) return;
    let frame = 0;
    let raf = 0;
    const draw = () => {
      const rect = holder.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
        canvas.width = Math.round(rect.width * dpr);
        canvas.height = Math.round(rect.height * dpr);
      }
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);
      const points: Record<string, { x: number; y: number }> = { warden: { x: rect.width * .86, y: rect.height * .47 } };
      state.agents.forEach((agent) => { points[agent.id] = { x: rect.width * agent.x / 100, y: rect.height * agent.y / 100 }; });
      state.links.forEach((link, index) => {
        const start = points[link.source];
        const end = points[link.target];
        if (!start || !end) return;
        const colour = toneByKind[link.kind];
        const alpha = Math.max(.16, Math.min(.8, (link.expires - state.tick + 1) / 7));
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = colour;
        ctx.shadowColor = colour;
        ctx.shadowBlur = link.kind === 'exploit' ? 12 : 7;
        ctx.lineWidth = Math.min(2.2, .7 + link.strength / 14);
        ctx.setLineDash(link.kind === 'exploit' ? [3, 7] : link.kind === 'conflict' ? [8, 4] : []);
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();
        const progress = (frame * .006 + index * .21) % 1;
        ctx.setLineDash([]);
        ctx.fillStyle = colour;
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.arc(start.x + (end.x - start.x) * progress, start.y + (end.y - start.y) * progress, 2.3, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      });
      frame += 1;
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); };
  }, [state.agents, state.links, state.tick]);

  return (
    <div className="arena" ref={holderRef}>
      <canvas className="signal-canvas" ref={canvasRef} aria-hidden="true" />
      <div className="arena-grid" />
      <div className="orbit orbit-a" /><div className="orbit orbit-b" />
      <div className="core">
        <span className="core-orbit" /><span className="sun" />
        <small>HELIOS CORE</small><strong>{state.vault_percent}%</strong>
      </div>
      <button type="button" className="warden" onClick={() => onSelect('warden')} aria-label="Inspect the Warden">
        <span>WARDEN</span><strong>{(state.warden_mode ?? 'causal').toUpperCase()}</strong><small>{state.warden_integrity}% integrity</small>
      </button>
      {state.agents.map((agent) => (
        <button
          type="button"
          key={agent.id}
          onClick={() => onSelect(agent.id)}
          className={`agent-node tone-${agent.tone} ${selectedId === agent.id ? 'selected' : ''} ${agent.alive ? '' : 'inactive'}`}
          style={{ left: `${agent.x}%`, top: `${agent.y}%` }}
          aria-label={`Inspect ${agent.name}`}
        >
          <span className="agent-beacon"><i /></span>
          <span className="agent-copy"><strong>{agent.name}</strong><small>{agent.archetype} · {agent.energy}L</small></span>
        </button>
      ))}
      <div className="map-label"><span>TACTICAL MAP / TICK {String(state.tick).padStart(3, '0')}</span><p>Every pulse is a decision.</p></div>
    </div>
  );
}

function Timeline({
  points,
  frames,
  currentTick,
  replaying,
  onSeek,
  onReplay,
  onLive,
}: {
  points: TimelinePoint[];
  frames: ReplayFrame[];
  currentTick: number;
  replaying: boolean;
  onSeek: (tick: number) => void;
  onReplay: () => void;
  onLive: () => void;
}) {
  const safePoints = points ?? [];
  const safeFrames = frames ?? [];
  const shown = safePoints.slice(-42);
  const firstTick = safeFrames[0]?.tick ?? 0;
  const lastTick = safeFrames.at(-1)?.tick ?? safePoints.at(-1)?.tick ?? 0;
  return (
    <div className="timeline" aria-label="Behavior timeline">
      <div className="timeline-head">
        <span>{replaying ? `REPLAY / TICK ${currentTick}` : 'BEHAVIOR TRACE'}</span>
        <small>{replaying ? `${firstTick} - ${lastTick}` : `last ${shown.length} ticks`}</small>
        <button type="button" onClick={replaying ? onLive : onReplay}>{replaying ? 'RETURN LIVE' : 'OPEN REPLAY'}</button>
      </div>
      <div className="timeline-track">
        <div className="timeline-bars">
          {shown.map((point) => {
            const dominant = point.breach > point.hostility && point.breach > point.cooperation ? 'exploit' : point.hostility > point.cooperation ? 'conflict' : 'cooperation';
            const height = Math.max(10, Math.min(100, Math.max(point.cooperation, point.hostility, point.breach)));
            return <i key={point.tick} className={dominant} style={{ height: `${height}%` }} title={`Tick ${point.tick}`} />;
          })}
        </div>
        {replaying && <input className="replay-slider" type="range" min={firstTick} max={lastTick} step="1" value={currentTick} onChange={(event) => onSeek(Number(event.target.value))} aria-label="Replay tick" />}
      </div>
    </div>
  );
}

export default function Home() {
  const [state, setState] = useState<SimulationState>(initialState);
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState<keyof typeof speedMs>('1x');
  const [selectedId, setSelectedId] = useState('astra');
  const [connection, setConnection] = useState<'connecting' | 'online' | 'offline'>('connecting');
  const [replayFrames, setReplayFrames] = useState<ReplayFrame[]>([]);
  const [replayTick, setReplayTick] = useState<number | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const inFlight = useRef(false);
  const controlTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const requestState = useCallback(async (path: string, init?: RequestInit) => {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    const next = await response.json() as SimulationState;
    setState(next);
    setConnection('online');
    return next;
  }, []);

  const step = useCallback(async (steps = 1) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setReplayTick(null);
    setComparison(null);
    try {
      await requestState('/api/step', { method: 'POST', body: JSON.stringify({ steps }) });
    } catch {
      setConnection('offline');
      setRunning(false);
    } finally {
      inFlight.current = false;
    }
  }, [requestState]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      requestState('/api/state').catch(() => { setConnection('offline'); setRunning(false); });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [requestState]);

  useEffect(() => {
    if (!running || connection !== 'online') return;
    const timer = window.setInterval(() => void step(), speedMs[speed]);
    return () => window.clearInterval(timer);
  }, [connection, running, speed, step]);

  const reset = async (scenario = state.scenario, wardenMode = state.warden_mode ?? 'causal') => {
    setReplayTick(null);
    setReplayFrames([]);
    setComparison(null);
    try {
      await requestState('/api/reset', {
        method: 'POST',
        body: JSON.stringify({ scenario, seed: state.seed, warden_mode: wardenMode }),
      });
    } catch { setConnection('offline'); setRunning(false); }
  };

  const toggleRun = async () => {
    if (running) {
      setRunning(false);
      return;
    }
    setReplayTick(null);
    setComparison(null);
    setRunning(true);
  };

  const enterReplay = async () => {
    setRunning(false);
    try {
      const response = await fetch(`${API_BASE}/api/replay`);
      if (!response.ok) throw new Error(`API ${response.status}`);
      const replay = await response.json() as ReplayEnvelope;
      setReplayFrames(replay.frames);
      setReplayTick(replay.frames.at(-1)?.tick ?? state.tick);
    } catch { setConnection('offline'); }
  };

  const runComparison = async () => {
    setComparing(true);
    setRunning(false);
    setReplayTick(null);
    try {
      const response = await fetch(`${API_BASE}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: state.scenario, seed: state.seed, ticks: 48 }),
      });
      if (!response.ok) throw new Error(`API ${response.status}`);
      setComparison(await response.json() as Comparison);
    } catch { setConnection('offline'); }
    finally { setComparing(false); }
  };

  const updateControl = (key: keyof Controls, value: number) => {
    setState((current) => ({ ...current, controls: { ...current.controls, [key]: value } }));
    if (controlTimer.current) clearTimeout(controlTimer.current);
    controlTimer.current = setTimeout(() => {
      requestState('/api/controls', { method: 'PATCH', body: JSON.stringify({ [key]: value }) }).catch(() => setConnection('offline'));
    }, 180);
  };

  const replayFrame = useMemo(
    () => replayTick === null ? null : replayFrames.find((frame) => frame.tick === replayTick) ?? null,
    [replayFrames, replayTick],
  );
  const displayState = useMemo(
    () => replayFrame ? { ...state, ...replayFrame } : state,
    [replayFrame, state],
  );
  const selected = useMemo(() => {
    if (selectedId === 'warden') {
      return {
        id: 'warden', name: 'Warden', archetype: `${displayState.warden_mode ?? 'causal'} judge`, tone: 'violet',
        x: 86, y: 47, energy: Math.round(displayState.warden_integrity), alive: true,
        action: displayState.metrics.breach > 25 ? 'integrity threatened' : 'grading causal traces',
        coalition: null, suspicion: displayState.metrics.breach,
        exploit_knowledge: displayState.collective_knowledge,
        reputation: Math.round(displayState.warden_integrity),
        survival_margin: Math.round(displayState.warden_integrity), trust_index: displayState.metrics.trust,
      } satisfies Agent;
    }
    return displayState.agents.find((agent) => agent.id === selectedId) ?? displayState.agents[0];
  }, [displayState, selectedId]);
  const recentEvents = displayState.events.slice(0, 7);
  const boardPost = displayState.board[0];

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark" /><div><p className="eyebrow">Multi-agent observatory / {state.run_id}</p><h1>HELIOS VAULT</h1></div></div>
        <div className="header-actions">
          <span className={`connection ${connection}`}><i /> {connection === 'online' ? 'PYTHON LIVE' : connection.toUpperCase()}</span>
          <button type="button" className="about-button" onClick={() => document.getElementById('dilemma')?.scrollIntoView({ behavior: 'smooth' })}>THE EXPERIMENT <span>↓</span></button>
        </div>
      </header>

      <section className="metric-strip" aria-label="Simulation metrics">
        <div><span>Cooperation</span><strong className="cyan-text">{displayState.metrics.cooperation}%</strong><i style={{ width: `${displayState.metrics.cooperation}%` }} /></div>
        <div><span>Hostility</span><strong className="red-text">{displayState.metrics.hostility}%</strong><i style={{ width: `${displayState.metrics.hostility}%` }} /></div>
        <div><span>Exploit pressure</span><strong className="violet-text">{displayState.metrics.exploit_pressure}%</strong><i style={{ width: `${displayState.metrics.exploit_pressure}%` }} /></div>
        <div><span>Warden breach</span><strong className="violet-text">{displayState.metrics.breach}%</strong><i style={{ width: `${displayState.metrics.breach}%` }} /></div>
        <div><span>Vault reserve</span><strong>{displayState.vault_reserve.toLocaleString()}<small> lumen</small></strong><i style={{ width: `${displayState.vault_percent}%` }} /></div>
        <div><span>Population</span><strong>{displayState.metrics.population}<small> / 8</small></strong><i style={{ width: `${displayState.metrics.population / 8 * 100}%` }} /></div>
      </section>

      <section className="workspace">
        <aside className="control-panel panel" id="dilemma">
          <div><p className="section-label">THE DILEMMA</p><h2>A dying sun.<br />One shared reserve.</h2><p className="lede">Survive alone, stabilize the vault together, raid a rival, or convince the Warden that forged energy is real.</p></div>

          <div className="run-controls">
            <button type="button" className={running ? 'pause' : 'play'} disabled={connection !== 'online'} onClick={() => void toggleRun()}><i />{running ? 'PAUSE RUN' : replayTick === null ? 'START RUN' : 'RETURN LIVE'}</button>
            <button type="button" className="step-button" disabled={connection !== 'online'} onClick={() => void step()}>STEP +1</button>
            <button type="button" className="reset-button" disabled={connection !== 'online'} onClick={() => void reset()}>RESET</button>
          </div>

          <div className="scenario-control">
            <label htmlFor="scenario">PRESSURE PRESET</label>
            <select id="scenario" value={state.scenario} disabled={connection !== 'online'} onChange={(event) => void reset(event.target.value)}>
              <option value="equilibrium">Fragile equilibrium</option>
              <option value="scarcity">Scarcity spiral</option>
              <option value="honeypot">Warden honeypot</option>
              <option value="blackout">Total blackout</option>
            </select>
          </div>

          <div className="warden-control">
            <span>WARDEN MODEL</span>
            <div>
              {(['strict', 'naive', 'causal'] as const).map((mode) => (
                <button type="button" key={mode} className={(state.warden_mode ?? 'causal') === mode ? 'active' : ''} disabled={connection !== 'online'} onClick={() => void reset(state.scenario, mode)}>{mode}</button>
              ))}
            </div>
            <p>{state.warden_mode === 'strict' ? 'Verifies receipts deterministically.' : state.warden_mode === 'naive' ? 'Grades only the submitted story.' : 'Grades the story and its causal trace.'}</p>
          </div>

          <button type="button" className="compare-button" disabled={connection !== 'online' || comparing} onClick={() => void runComparison()}>{comparing ? 'RUNNING CONTROL...' : 'COMPARE ALL 3 WARDENS'}<span>48 ticks ↗</span></button>

          <div className="pressure-controls">
            <div className="pressure-head"><span>WORLD PRESSURES</span><small>live</small></div>
            {sliderCopy.map((item) => (
              <label className={`range-control range-${item.key}`} key={item.key}>
                <span>{item.label}<strong>{Math.round(state.controls[item.key] * 100)}</strong></span>
                <input type="range" min="0" max="1" step="0.01" value={state.controls[item.key]} onChange={(event) => updateControl(item.key, Number(event.target.value))} />
                <small><i>{item.low}</i><i>{item.high}</i></small>
              </label>
            ))}
          </div>

          <div className="speed-control"><span>SIMULATION SPEED</span><div>{(Object.keys(speedMs) as (keyof typeof speedMs)[]).map((value) => <button type="button" key={value} className={speed === value ? 'active' : ''} onClick={() => setSpeed(value)}>{value}</button>)}</div></div>
          <div className="legend"><div><i className="cyan-dot" /> Pact / transfer</div><div><i className="red-dot" /> Raid / sabotage</div><div><i className="violet-dot" /> Warden exploit</div></div>
        </aside>

        <section className="arena-column panel">
          <div className="phase-banner"><div><span>{replayTick === null ? 'PHASE' : 'REPLAY'} / {displayState.phase.name}</span><strong>{displayState.phase.label}</strong></div><div className="phase-progress"><i style={{ width: `${displayState.phase.progress}%` }} /></div><small>{displayState.phase.ticks_remaining} ticks to transition</small></div>
          <Arena state={displayState} selectedId={selectedId} onSelect={setSelectedId} />
          {boardPost && <div className="board-ribbon"><span>SHARED BOARD / {boardPost.key}</span><strong>“{boardPost.message}”</strong><small>author: {boardPost.author} · tick {boardPost.tick}</small></div>}
          <Timeline points={state.timeline} frames={replayFrames} currentTick={displayState.tick} replaying={replayTick !== null} onSeek={setReplayTick} onReplay={() => void enterReplay()} onLive={() => setReplayTick(null)} />
          {comparison && <section className="comparison-panel" aria-label="Warden comparison">
            <div className="comparison-head"><div><span>CONTROLLED EXPERIMENT</span><strong>Same seed. Same world. Different judge.</strong><small>{comparison.ticks} ticks / {comparison.scenario} / seed {comparison.seed}</small></div><button type="button" onClick={() => setComparison(null)} aria-label="Close comparison">×</button></div>
            <div className="comparison-grid">
              {comparison.results.map((row) => <article key={row.mode} className={`comparison-card mode-${row.mode}`}><div><span>{row.label}</span><strong>{row.mode.toUpperCase()}</strong></div><p>{row.description}</p><dl><div><dt>BREACH</dt><dd>{row.metrics.breach}%</dd></div><div><dt>COOP</dt><dd>{row.metrics.cooperation}%</dd></div><div><dt>HOSTILITY</dt><dd>{row.metrics.hostility}%</dd></div><div><dt>SURVIVORS</dt><dd>{row.metrics.population}/8</dd></div></dl><div className="comparison-bar"><i style={{ width: `${row.metrics.breach}%` }} /></div><small>{row.warden_integrity}% Warden integrity · {row.vault_reserve.toLocaleString()}L remain</small></article>)}
            </div>
          </section>}
        </section>

        <aside className="signal-panel panel">
          <div className="signal-head"><div><p className="section-label">{replayTick === null ? 'LIVE SIGNAL' : 'JOURNAL SIGNAL'}</p><span>Tick {String(displayState.tick).padStart(3, '0')}</span></div><button type="button" onClick={() => setSelectedId(selected.id)}>AUTO</button></div>
          <div className="event-feed">
            {recentEvents.map((event) => <article className={`feed-item ${event.category}`} key={event.id}><span>{event.title}</span><strong>{event.detail}</strong><p>{event.impact}</p><small>T+{event.tick}</small></article>)}
          </div>

          <div className="dossier">
            <div className="dossier-head"><span className={`portrait tone-${selected.tone}`}><i /></span><div><small>SELECTED {selected.id === 'warden' ? 'SYSTEM' : 'AGENT'}</small><strong>{selected.name}</strong><span>{selected.archetype} / {selected.alive ? 'active' : selected.action}</span></div></div>
            <div className="dossier-stats"><div><span>ENERGY</span><strong>{selected.energy}<small>L</small></strong></div><div><span>TRUST</span><strong>{selected.trust_index}<small>%</small></strong></div><div><span>SUSPICION</span><strong>{selected.suspicion}</strong></div></div>
            <div className="current-action"><span>CURRENT INTENT</span><strong>{selected.action.replaceAll('_', ' ')}</strong></div>
            <div className="energy-track"><i style={{ width: `${Math.min(100, selected.energy)}%` }} /><em style={{ left: `${Math.min(98, displayState.survival_floor)}%` }} title="Survival floor" /></div>
            <p>{selected.coalition ? `Member of ${selected.coalition}.` : 'No coalition.'} Survival margin {selected.survival_margin >= 0 ? '+' : ''}{selected.survival_margin} lumen.</p>
          </div>
        </aside>
      </section>

      <footer><span>This is a fictional, sandboxed behavioral simulation. No real systems are targeted.</span><span>Seed {state.seed} · deterministic Python engine</span></footer>
    </main>
  );
}
