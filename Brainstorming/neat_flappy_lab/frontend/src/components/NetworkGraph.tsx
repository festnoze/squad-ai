import { useEffect, useMemo, useRef } from 'react'
import * as d3 from 'd3'
import { useLab } from '../store'
import { CAMP_COLORS, CAMP_LABELS } from '../camps'
import type { Genome, GenomeNode } from '../types'

/** A simulated node = the genome node plus d3-force layout fields. */
interface SimNode extends GenomeNode, d3.SimulationNodeDatum {
  id: number
}

/** A simulated link referencing node ids (resolved by d3.forceLink). */
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  source: number | SimNode
  target: number | SimNode
  weight: number
}

const NODE_RADIUS = 11

const NODE_COLORS: Record<GenomeNode['type'], string> = {
  input: 'var(--node-input)',
  bias: 'var(--node-bias)',
  hidden: 'var(--node-hidden)',
  output: 'var(--node-output)',
}

const LEGEND: { type: GenomeNode['type']; label: string }[] = [
  { type: 'input', label: 'Entrée' },
  { type: 'bias', label: 'Biais' },
  { type: 'hidden', label: 'Caché' },
  { type: 'output', label: 'Sortie' },
]

/**
 * A stable signature for the genome *topology*. When this string changes we
 * rebuild the DOM + restart the force simulation; otherwise (e.g. only live
 * activations changed) we leave the layout alone and just repaint.
 */
function topologySignature(g: Genome | null): string {
  if (!g) return ''
  // node ids + enabled connection (in,out) pairs — order-independent enough
  // for our purpose since NEAT appends nodes/conns deterministically.
  const nodes = g.nodes.map((n) => `${n.id}:${n.type}`).join(',')
  const conns = g.connections
    .filter((c) => c.enabled)
    .map((c) => `${c.in}>${c.out}`)
    .join(',')
  return `${nodes}|${conns}`
}

export function NetworkGraph() {
  const selectedGenome = useLab((s) => s.selectedGenome)
  const bestGenome = useLab((s) => s.bestGenome)
  const frame = useLab((s) => s.frame)

  const genome = selectedGenome ?? bestGenome

  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)

  // Persistent layout state across renders.
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null)
  const nodeSelRef = useRef<d3.Selection<SVGGElement, SimNode, SVGGElement, unknown> | null>(null)
  const sizeRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 })

  const signature = useMemo(() => topologySignature(genome), [genome])

  // --- (Re)build layout + DOM when topology or size changes ------------------
  useEffect(() => {
    const wrapper = wrapperRef.current
    const svgEl = svgRef.current
    if (!wrapper || !svgEl || !genome) return

    const svg = d3.select(svgEl)
    // StrictMode double-mounts; always clear so we never duplicate the DOM.
    svg.selectAll('*').remove()
    nodeSelRef.current = null
    if (simRef.current) {
      simRef.current.stop()
      simRef.current = null
    }

    let w = wrapper.clientWidth
    let h = wrapper.clientHeight

    function sync(width: number, height: number) {
      w = Math.max(1, width)
      h = Math.max(1, height)
      sizeRef.current = { w, h }
      svg.attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`)
    }
    sync(w, h)

    // Fresh node/link arrays (clones so d3 can mutate them freely).
    const nodes: SimNode[] = genome.nodes.map((n) => ({ ...n }))
    const links: SimLink[] = genome.connections
      .filter((c) => c.enabled)
      .map((c) => ({ source: c.in, target: c.out, weight: c.weight }))

    // Per-node horizontal target so the feed-forward layering reads clearly.
    const targetX = (n: SimNode) => {
      if (n.type === 'input' || n.type === 'bias') return w * 0.12
      if (n.type === 'output') return w * 0.88
      return w * 0.5
    }
    // Inputs/outputs are pinned hard so the columns stay crisp; hidden float.
    const strengthX = (n: SimNode) =>
      n.type === 'hidden' ? 0.08 : 0.9

    const sim = d3
      .forceSimulation<SimNode, SimLink>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(60)
          .strength(0.25),
      )
      .force('charge', d3.forceManyBody<SimNode>().strength(-120))
      .force('x', d3.forceX<SimNode>(targetX).strength(strengthX))
      .force('y', d3.forceY<SimNode>(h / 2).strength(0.06))
      .force('collide', d3.forceCollide<SimNode>(NODE_RADIUS + 6))
      .alpha(1)
      .alphaDecay(0.06)

    simRef.current = sim

    const margin = NODE_RADIUS + 4
    const clamp = (v: number, lo: number, hi: number) =>
      Math.max(lo, Math.min(hi, v))

    // --- Edges -------------------------------------------------------------
    const linkSel = svg
      .append('g')
      .attr('class', 'edges')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(links)
      .join('line')
      .attr('stroke', (d) => (d.weight >= 0 ? 'var(--edge-pos)' : 'var(--edge-neg)'))
      .attr('stroke-width', (d) => 0.5 + Math.min(Math.abs(d.weight), 4))
      .attr('stroke-opacity', 0.45)
      .attr('stroke-linecap', 'round')

    // --- Nodes (group = halo circle + core circle) -------------------------
    const nodeSel = svg
      .append('g')
      .attr('class', 'nodes')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('class', 'node')

    nodeSel
      .append('circle')
      .attr('class', 'halo')
      .attr('r', NODE_RADIUS + 7)
      .attr('fill', (d) => NODE_COLORS[d.type])
      .attr('opacity', 0) // driven by live activations

    nodeSel
      .append('circle')
      .attr('class', 'core')
      .attr('r', NODE_RADIUS)
      .attr('fill', (d) => NODE_COLORS[d.type])
      .attr('stroke', '#0c1018')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.92)

    nodeSel.append('title').text((d) => `#${d.id} · ${d.type} · ${d.activation}`)

    nodeSelRef.current = nodeSel

    // --- Tick: clamp into view + position everything -----------------------
    sim.on('tick', () => {
      nodes.forEach((n) => {
        n.x = clamp(n.x ?? w / 2, margin, w - margin)
        n.y = clamp(n.y ?? h / 2, margin, h - margin)
      })
      linkSel
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!)
      nodeSel.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    // Settle quickly: run a burst of ticks synchronously, then let it cool.
    sim.tick(60)
    sim.alpha(0.3).restart()

    // --- Keep SVG sized to the panel --------------------------------------
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect
      if (!cr) return
      sync(cr.width, cr.height)
      // Re-aim the horizontal/vertical forces for the new dimensions.
      const fx = sim.force('x') as d3.ForceX<SimNode> | undefined
      const fy = sim.force('y') as d3.ForceY<SimNode> | undefined
      fx?.x(targetX)
      fy?.y(h / 2)
      sim.alpha(0.3).restart()
    })
    ro.observe(wrapper)

    return () => {
      ro.disconnect()
      sim.stop()
      simRef.current = null
      nodeSelRef.current = null
      svg.selectAll('*').remove()
    }
    // Rebuild only when topology identity changes. Size is handled internally
    // by the ResizeObserver, so it is intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])

  // --- Cheap per-frame repaint of live activations (no sim restart) ---------
  useEffect(() => {
    const nodeSel = nodeSelRef.current
    if (!nodeSel) return

    const acts = frame?.selectedActivations

    nodeSel.each(function (d) {
      const g = d3.select(this)
      const raw = acts ? acts[String(d.id)] : undefined
      if (raw === undefined || raw === null || Number.isNaN(raw)) {
        g.select<SVGCircleElement>('circle.halo').attr('opacity', 0)
        g.select<SVGCircleElement>('circle.core').attr('opacity', 0.92)
        return
      }
      const mag = Math.min(Math.abs(raw), 1) // activations are ~[-1,1]
      // Glow halo scales with activation strength; core brightens too.
      g.select<SVGCircleElement>('circle.halo').attr('opacity', mag * 0.55)
      g.select<SVGCircleElement>('circle.core').attr('opacity', 0.55 + mag * 0.45)
    })
  }, [frame])

  // --- Empty state ----------------------------------------------------------
  if (!genome) {
    return (
      <div className="empty-hint">
        Sélectionnez un oiseau ou lancez l'évolution pour voir un réseau.
      </div>
    )
  }

  return (
    <div className="fill" ref={wrapperRef}>
      <svg ref={svgRef} style={{ display: 'block' }} />
      {genome.camp && (
        <span
          style={{
            position: 'absolute',
            right: 12,
            top: 10,
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.06em',
            padding: '2px 8px',
            borderRadius: 999,
            border: `1px solid ${CAMP_COLORS[genome.camp]}`,
            color: CAMP_COLORS[genome.camp],
          }}
          title={
            genome.camp === 'neat'
              ? 'Réseau façonné par évolution (NEAT)'
              : genome.camp === 'gd'
                ? 'Réseau entraîné par descente de gradient'
                : 'Réseau hybride évolution + gradient'
          }
        >
          {CAMP_LABELS[genome.camp]}
        </span>
      )}
      <div
        className="legend"
        style={{ position: 'absolute', left: 12, bottom: 10 }}
      >
        {LEGEND.map((l) => (
          <span className="swatch" key={l.type}>
            <i style={{ background: NODE_COLORS[l.type] }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  )
}
