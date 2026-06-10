import { useEffect, useRef } from 'react'
import { useLab } from '../store'
import { CAMP_COLORS, CAMP_LABELS } from '../camps'
import type { Camp, FrameMsg, World } from '../types'

const PIPE_WIDTH = 60 // world units
const BIRD_RADIUS = 10 // world units

/** Resolve a CSS custom property to a usable color string (with fallback). */
function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

interface Transform {
  scale: number
  offsetX: number
  offsetY: number
}

/** Compute an aspect-preserving, centered (letterboxed) world->canvas transform. */
function computeTransform(world: World, cssW: number, cssH: number): Transform {
  const scale = Math.min(cssW / world.w, cssH / world.h)
  const offsetX = (cssW - world.w * scale) / 2
  const offsetY = (cssH - world.h * scale) / 2
  return { scale, offsetX, offsetY }
}

export function GameCanvas() {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  // CSS pixel size of the canvas, kept in a ref so the rAF loop reads fresh values.
  const sizeRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 })
  // Latest transform, stored so the click handler can map screen->world.
  const transformRef = useRef<Transform | null>(null)
  // We must subscribe to `frame` so React re-mounts/re-renders the empty state,
  // but the actual drawing reads the freshest value from the store each frame.
  const frame = useLab((s) => s.frame)
  const playing = useLab((s) => s.playing)

  // ---- canvas sizing + DPR handling + rAF draw loop -------------------------
  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0

    const resize = () => {
      const rect = wrap.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      const cssW = Math.max(1, Math.floor(rect.width))
      const cssH = Math.max(1, Math.floor(rect.height))
      sizeRef.current = { w: cssW, h: cssH }
      canvas.width = Math.floor(cssW * dpr)
      canvas.height = Math.floor(cssH * dpr)
      canvas.style.width = `${cssW}px`
      canvas.style.height = `${cssH}px`
      // Draw in CSS pixels; scale the backing store for crispness.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(wrap)

    // Resolve theme colors once (cheap; avoids per-frame getComputedStyle).
    const colBg = cssVar('--bg-elev-2', '#1a2333')
    const colGrid = cssVar('--divider', '#1e2840')
    const colPipe = '#2f6b5e' // muted green/teal for pipes
    const colPipeEdge = cssVar('--accent-strong', '#2cc4b6')
    const colAccent = cssVar('--accent', '#4fd1c5')
    const colTextDim = cssVar('--text-dim', '#9fb0c8')

    const draw = () => {
      raf = requestAnimationFrame(draw)
      const { w: cssW, h: cssH } = sizeRef.current
      if (cssW === 0 || cssH === 0) return

      // Background.
      ctx.clearRect(0, 0, cssW, cssH)
      ctx.fillStyle = colBg
      ctx.fillRect(0, 0, cssW, cssH)

      const f: FrameMsg | null = useLab.getState().frame
      const world = f?.world
      if (!f || !world) {
        transformRef.current = null
        return
      }

      const t = computeTransform(world, cssW, cssH)
      transformRef.current = t
      const { scale, offsetX, offsetY } = t
      const toX = (wx: number) => offsetX + wx * scale
      const toY = (wy: number) => offsetY + wy * scale

      // Clip to the world rectangle so pipes/birds never bleed into letterbox bars.
      ctx.save()
      ctx.beginPath()
      ctx.rect(offsetX, offsetY, world.w * scale, world.h * scale)
      ctx.clip()

      // Faint grid (world-aligned).
      ctx.strokeStyle = colGrid
      ctx.lineWidth = 1
      ctx.globalAlpha = 0.4
      const step = 50
      for (let gx = 0; gx <= world.w; gx += step) {
        ctx.beginPath()
        ctx.moveTo(toX(gx), toY(0))
        ctx.lineTo(toX(gx), toY(world.h))
        ctx.stroke()
      }
      for (let gy = 0; gy <= world.h; gy += step) {
        ctx.beginPath()
        ctx.moveTo(toX(0), toY(gy))
        ctx.lineTo(toX(world.w), toY(gy))
        ctx.stroke()
      }
      ctx.globalAlpha = 1

      // Pipes: two rectangles per pipe, gap left empty.
      const pw = PIPE_WIDTH * scale
      for (const p of f.pipes) {
        const px = toX(p.x)
        const topBottom = p.gapY - p.gapH / 2 // world y where top pipe ends
        const botTop = p.gapY + p.gapH / 2 // world y where bottom pipe starts

        ctx.fillStyle = colPipe
        // Top pipe: from world y=0 down to topBottom.
        const topH = (topBottom - 0) * scale
        if (topH > 0) ctx.fillRect(px, toY(0), pw, topH)
        // Bottom pipe: from botTop down to world.h.
        const botH = (world.h - botTop) * scale
        if (botH > 0) ctx.fillRect(px, toY(botTop), pw, botH)

        // Subtle lip on the gap edges.
        ctx.fillStyle = colPipeEdge
        const lip = Math.max(2, 4 * scale)
        if (topH > 0) ctx.fillRect(px, toY(topBottom) - lip, pw, lip)
        if (botH > 0) ctx.fillRect(px, toY(botTop), pw, lip)
      }

      // Birds: semi-transparent flock colored by training camp (NEAT / GD /
      // hybrid); the selected bird is drawn opaque + highlighted on top.
      const selectedId = useLab.getState().selectedBirdId
      const r = BIRD_RADIUS * scale
      let selected: (typeof f.birds)[number] | null = null
      const campColor = (camp: Camp | undefined) =>
        camp ? CAMP_COLORS[camp] : colAccent

      for (const b of f.birds) {
        if (!b.alive) continue
        if (b.id === selectedId) {
          selected = b
          continue // draw on top afterwards
        }
        ctx.fillStyle = campColor(b.camp)
        ctx.globalAlpha = 0.35
        ctx.beginPath()
        ctx.arc(toX(b.x), toY(b.y), r, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1

      if (selected && selected.alive) {
        const sx = toX(selected.x)
        const sy = toY(selected.y)
        const selColor = campColor(selected.camp)
        // Halo.
        ctx.globalAlpha = 0.25
        ctx.fillStyle = selColor
        ctx.beginPath()
        ctx.arc(sx, sy, r * 2.2, 0, Math.PI * 2)
        ctx.fill()
        ctx.globalAlpha = 1
        // Opaque body.
        ctx.fillStyle = selColor
        ctx.beginPath()
        ctx.arc(sx, sy, r, 0, Math.PI * 2)
        ctx.fill()
        // Bright ring.
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = Math.max(1.5, 2 * scale)
        ctx.beginPath()
        ctx.arc(sx, sy, r + Math.max(2, 3 * scale), 0, Math.PI * 2)
        ctx.stroke()
        // Star marker above the bird.
        ctx.fillStyle = '#ffffff'
        ctx.font = `${Math.max(10, 14 * scale)}px Inter, system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        ctx.fillText('★', sx, sy - r - 4)
      }

      ctx.restore() // remove world clip before HUD

      // HUD (top-left), in CSS pixels.
      ctx.fillStyle = colTextDim
      ctx.font = '12px Inter, system-ui, sans-serif'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'top'
      ctx.fillText(`gén ${f.gen}  ·  tick ${f.tick}`, 10, 8)
      ctx.fillText(`vivants ${f.aliveCount} / ${f.birds.length}`, 10, 24)

      // Per-camp legend + live alive counts, when birds carry a camp tag.
      const campCounts = new Map<Camp, { alive: number; total: number }>()
      for (const b of f.birds) {
        if (!b.camp) continue
        const c = campCounts.get(b.camp) ?? { alive: 0, total: 0 }
        c.total += 1
        if (b.alive) c.alive += 1
        campCounts.set(b.camp, c)
      }
      let hudY = 44
      for (const [camp, c] of campCounts) {
        ctx.fillStyle = CAMP_COLORS[camp]
        ctx.beginPath()
        ctx.arc(15, hudY + 6, 4, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillText(`${CAMP_LABELS[camp]}  ${c.alive} / ${c.total}`, 26, hudY)
        hudY += 16
      }
    }

    raf = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [])

  // ---- click -> select nearest (by world Y, since all birds share x) --------
  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    const t = transformRef.current
    const f = useLab.getState().frame
    if (!canvas || !t || !f) return

    const rect = canvas.getBoundingClientRect()
    const cy = e.clientY - rect.top
    // Inverse transform: canvas Y -> world Y.
    const worldY = (cy - t.offsetY) / t.scale

    let best: number | null = null
    let bestDist = Infinity
    for (const b of f.birds) {
      if (!b.alive) continue
      const d = Math.abs(b.y - worldY)
      if (d < bestDist) {
        bestDist = d
        best = b.id
      }
    }
    if (best !== null) useLab.getState().select(best)
  }

  return (
    <div className="fill" ref={wrapRef}>
      <canvas
        ref={canvasRef}
        onClick={onClick}
        style={{ display: 'block', cursor: 'crosshair' }}
      />
      {!frame && (
        <div className="empty-hint">
          {playing ? (
            <div className="spinner-block">
              <span className="spinner lg" />
              Démarrage de la simulation…
            </div>
          ) : (
            <>En attente de la simulation… (lancez «&nbsp;Play&nbsp;»)</>
          )}
        </div>
      )}
    </div>
  )
}
