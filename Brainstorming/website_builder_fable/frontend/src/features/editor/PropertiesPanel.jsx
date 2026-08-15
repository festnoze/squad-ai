// OWNED BY: frontend-editor agent.
// Right-hand properties panel: Content fields (updateBlockProps) and Style
// fields (updateBlockStyle) per the matrix in docs/decisions-editor.md section 6.
// Style edits apply immediately as inline CSS through the toCss pipeline.

import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client.js'
import { useEditorStore } from './editorStore.js'
import { findNode } from './treeUtils.js'
import { BLOCK_DEFINITIONS, createDefault } from './blockDefinitions.js'
import AssetPicker from './AssetPicker.jsx'

/* ---------- reusable field widgets ---------- */

function TextField({ label, value, onChange, placeholder }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input
        className="input"
        value={value ?? ''}
        placeholder={placeholder || ''}
        onChange={e => onChange(e.target.value)}
      />
    </div>
  )
}

function TextAreaField({ label, value, onChange, rows = 4 }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <textarea
        className="textarea"
        rows={rows}
        value={value ?? ''}
        onChange={e => onChange(e.target.value)}
      />
    </div>
  )
}

function NumberField({ label, value, onChange, min, max, step = 1 }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input
        className="input"
        type="number"
        value={value ?? ''}
        min={min}
        max={max}
        step={step}
        onChange={e => {
          if (e.target.value === '') return
          let n = Number(e.target.value)
          if (!Number.isFinite(n)) return
          if (min !== undefined) n = Math.max(min, n)
          if (max !== undefined) n = Math.min(max, n)
          onChange(n)
        }}
      />
    </div>
  )
}

function ColorField({ label, value, onChange }) {
  const hex = /^#[0-9a-fA-F]{6}$/.test(value || '') ? value : '#000000'
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="color-field">
        <input type="color" value={hex} onChange={e => onChange(e.target.value)} />
        <input
          className="input"
          value={value ?? ''}
          placeholder="#000000 or transparent"
          onChange={e => onChange(e.target.value)}
        />
      </div>
    </div>
  )
}

function SelectField({ label, value, onChange, options }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <select className="select" value={value ?? ''} onChange={e => onChange(e.target.value)}>
        {options.map(opt => (
          <option key={String(opt.value)} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  )
}

function AlignField({ label, value, onChange }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="align-group">
        {['left', 'center', 'right'].map(a => (
          <button
            key={a}
            type="button"
            className={'btn btn-sm' + (value === a ? ' align-active' : '')}
            onClick={() => onChange(a)}
          >
            {a}
          </button>
        ))}
      </div>
    </div>
  )
}

// Four number inputs (top/right/bottom/left) writing individual px style keys.
function SpacingGroup({ label, prefix, style, onChangeKey }) {
  const sides = ['Top', 'Right', 'Bottom', 'Left']
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="spacing-grid">
        {sides.map(side => {
          const key = prefix + side
          return (
            <label key={key} className="spacing-cell">
              <span>{side[0]}</span>
              <input
                className="input"
                type="number"
                value={style[key] ?? ''}
                onChange={e => {
                  if (e.target.value === '') return
                  const n = Number(e.target.value)
                  if (Number.isFinite(n)) onChangeKey(key, n)
                }}
              />
            </label>
          )
        })}
      </div>
    </div>
  )
}

// Accepts px numbers or strings like "100%" / "960px" for width-ish keys.
function DimensionField({ label, value, onChange }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input
        className="input"
        value={value ?? ''}
        placeholder="e.g. 100% or 640"
        onChange={e => {
          const raw = e.target.value
          onChange(/^\d+$/.test(raw) ? Number(raw) : raw)
        }}
      />
    </div>
  )
}

const FONT_WEIGHT_OPTIONS = [400, 500, 600, 700, 800].map(w => ({ value: w, label: String(w) }))

/* ---------- content editors ---------- */

function RowColumnsEditor({ node }) {
  const insertBlock = useEditorStore(s => s.insertBlock)
  const removeBlock = useEditorStore(s => s.removeBlock)
  const count = node.children.length
  const last = node.children[count - 1]
  const canRemove = count > 1 && !!last && last.children.length === 0
  return (
    <div className="field">
      <label className="field-label">Columns</label>
      <div className="stepper">
        <button
          type="button"
          className="btn btn-sm"
          disabled={!canRemove}
          title={canRemove ? 'Remove last column' : 'Last column must be empty to remove it'}
          onClick={() => removeBlock(last.id)}
        >
          -
        </button>
        <span className="stepper-value">{count}</span>
        <button
          type="button"
          className="btn btn-sm"
          disabled={count >= 4}
          title="Add a column"
          onClick={() => insertBlock(node.id, count, createDefault('column'))}
        >
          +
        </button>
      </div>
      {count > 1 && !canRemove ? (
        <div className="muted panel-hint">Empty the last column before removing it.</div>
      ) : null}
    </div>
  )
}

function LinksEditor({ node }) {
  const updateBlockProps = useEditorStore(s => s.updateBlockProps)
  const links = Array.isArray(node.props.links) ? node.props.links : []
  const setLinks = next => updateBlockProps(node.id, { links: next })
  return (
    <div className="field">
      <label className="field-label">Links</label>
      {links.map((link, i) => (
        <div key={i} className="link-row">
          <input
            className="input"
            value={link.label ?? ''}
            placeholder="Label"
            onChange={e => setLinks(links.map((l, j) => (j === i ? { ...l, label: e.target.value } : l)))}
          />
          <input
            className="input"
            value={link.href ?? ''}
            placeholder="Href"
            onChange={e => setLinks(links.map((l, j) => (j === i ? { ...l, href: e.target.value } : l)))}
          />
          <button
            type="button"
            className="btn btn-sm"
            title="Remove link"
            onClick={() => setLinks(links.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => setLinks([...links, { label: 'Link', href: '#' }])}
      >
        Add link
      </button>
    </div>
  )
}

function ImageContentEditor({ node }) {
  const projectId = useEditorStore(s => s.projectId)
  const updateBlockProps = useEditorStore(s => s.updateBlockProps)
  const [pickerOpen, setPickerOpen] = useState(false)
  return (
    <>
      <TextField
        label="Source URL"
        value={node.props.src}
        placeholder="https://... or /api/uploads/..."
        onChange={v => updateBlockProps(node.id, { src: v })}
      />
      <div className="field">
        <button type="button" className="btn btn-sm" onClick={() => setPickerOpen(true)}>
          Choose from assets
        </button>
      </div>
      <TextField
        label="Alt text"
        value={node.props.alt}
        onChange={v => updateBlockProps(node.id, { alt: v })}
      />
      {pickerOpen && (
        <AssetPicker
          projectId={projectId}
          onClose={() => setPickerOpen(false)}
          onPick={asset => {
            updateBlockProps(node.id, { src: asset.url })
            setPickerOpen(false)
          }}
        />
      )}
    </>
  )
}

function CollectionListEditor({ node }) {
  const projectId = useEditorStore(s => s.projectId)
  const updateBlockProps = useEditorStore(s => s.updateBlockProps)
  const [collections, setCollections] = useState([])

  useEffect(() => {
    let alive = true
    if (!projectId) return undefined
    apiGet(`/api/projects/${projectId}/collections`)
      .then(list => { if (alive) setCollections(list || []) })
      .catch(() => { if (alive) setCollections([]) })
    return () => { alive = false }
  }, [projectId])

  const collectionId = node.props.collectionId
  const itemTemplate = node.props.itemTemplate || { title: null, text: null, image: null }
  const current = collections.find(c => c.id === collectionId)
  const fields = current ? current.fields || [] : []
  const imageFields = fields.filter(f => f.type === 'image')

  const fieldOptions = list => [
    { value: '', label: '(none)' },
    ...list.map(f => ({ value: f.key, label: f.label + ' (' + f.key + ')' })),
  ]

  const setSlot = (slot, value) =>
    updateBlockProps(node.id, { itemTemplate: { ...itemTemplate, [slot]: value || null } })

  return (
    <>
      <SelectField
        label="Collection"
        value={collectionId ?? ''}
        options={[
          { value: '', label: '(not bound)' },
          ...collections.map(c => ({ value: c.id, label: c.name })),
        ]}
        onChange={v =>
          updateBlockProps(node.id, {
            collectionId: v === '' ? null : Number(v),
            itemTemplate: { title: null, text: null, image: null },
          })
        }
      />
      <NumberField
        label="Limit"
        value={node.props.limit ?? 6}
        min={1}
        max={50}
        onChange={v => updateBlockProps(node.id, { limit: v })}
      />
      {current ? (
        <>
          <SelectField
            label="Title slot"
            value={itemTemplate.title ?? ''}
            options={fieldOptions(fields)}
            onChange={v => setSlot('title', v)}
          />
          <SelectField
            label="Text slot"
            value={itemTemplate.text ?? ''}
            options={fieldOptions(fields)}
            onChange={v => setSlot('text', v)}
          />
          <SelectField
            label="Image slot"
            value={itemTemplate.image ?? ''}
            options={fieldOptions(imageFields)}
            onChange={v => setSlot('image', v)}
          />
        </>
      ) : (
        <div className="muted panel-hint">Bind a collection to map its fields.</div>
      )}
    </>
  )
}

function ContentSection({ node }) {
  const updateBlockProps = useEditorStore(s => s.updateBlockProps)
  const set = patch => updateBlockProps(node.id, patch)
  switch (node.type) {
    case 'heading':
      return (
        <>
          <TextField label="Text" value={node.props.text} onChange={v => set({ text: v })} />
          <SelectField
            label="Level"
            value={node.props.level ?? 2}
            options={[1, 2, 3, 4].map(l => ({ value: l, label: 'H' + l }))}
            onChange={v => set({ level: Number(v) })}
          />
        </>
      )
    case 'text':
      return <TextAreaField label="HTML content" value={node.props.html} rows={6} onChange={v => set({ html: v })} />
    case 'image':
      return <ImageContentEditor node={node} />
    case 'button':
      return (
        <>
          <TextField label="Label" value={node.props.label} onChange={v => set({ label: v })} />
          <TextField label="Link (href)" value={node.props.href} onChange={v => set({ href: v })} />
        </>
      )
    case 'navbar':
      return (
        <>
          <TextField label="Brand" value={node.props.brand} onChange={v => set({ brand: v })} />
          <LinksEditor node={node} />
        </>
      )
    case 'footer':
      return <TextAreaField label="Text" value={node.props.text} rows={3} onChange={v => set({ text: v })} />
    case 'form':
      return (
        <>
          <TextField label="Title" value={node.props.title} onChange={v => set({ title: v })} />
          <TextField label="Submit label" value={node.props.submitLabel} onChange={v => set({ submitLabel: v })} />
          <div className="field">
            <label className="field-label">Fields (fixed)</label>
            <div className="muted mono">name, email, message</div>
          </div>
        </>
      )
    case 'collectionList':
      return <CollectionListEditor node={node} />
    case 'row':
      return <RowColumnsEditor node={node} />
    case 'column':
      return (
        <NumberField
          label="Width fraction (1-12)"
          value={node.props.widthFraction ?? 1}
          min={1}
          max={12}
          onChange={v => set({ widthFraction: v })}
        />
      )
    default:
      return <div className="muted panel-hint">This block has no content settings.</div>
  }
}

/* ---------- style editors ---------- */

function StyleSection({ node }) {
  const updateBlockStyle = useEditorStore(s => s.updateBlockStyle)
  const style = node.style || {}
  const set = (key, value) => updateBlockStyle(node.id, { [key]: value })

  const padding = <SpacingGroup label="Padding (px)" prefix="padding" style={style} onChangeKey={set} />
  const margin = <SpacingGroup label="Margin (px)" prefix="margin" style={style} onChangeKey={set} />
  const marginTB = (
    <>
      <NumberField label="Margin top (px)" value={style.marginTop} onChange={v => set('marginTop', v)} />
      <NumberField label="Margin bottom (px)" value={style.marginBottom} onChange={v => set('marginBottom', v)} />
    </>
  )
  const bg = <ColorField label="Background color" value={style.backgroundColor} onChange={v => set('backgroundColor', v)} />
  const textColor = <ColorField label="Text color" value={style.color} onChange={v => set('color', v)} />
  const fontSize = <NumberField label="Font size (px)" value={style.fontSize} onChange={v => set('fontSize', v)} min={8} />
  const fontWeight = (
    <SelectField
      label="Font weight"
      value={style.fontWeight ?? 400}
      options={FONT_WEIGHT_OPTIONS}
      onChange={v => set('fontWeight', Number(v))}
    />
  )
  const align = <AlignField label="Text align" value={style.textAlign} onChange={v => set('textAlign', v)} />
  const radius = <NumberField label="Border radius (px)" value={style.borderRadius} min={0} onChange={v => set('borderRadius', v)} />
  const gap = <NumberField label="Gap (px)" value={style.gap} min={0} onChange={v => set('gap', v)} />

  switch (node.type) {
    case 'section':
      return (
        <>
          {padding}
          {marginTB}
          {bg}
          {radius}
          <DimensionField label="Max width" value={style.maxWidth} onChange={v => set('maxWidth', v)} />
        </>
      )
    case 'row':
      return <>{gap}{padding}{bg}</>
    case 'column':
      return <>{padding}{bg}{radius}</>
    case 'heading':
    case 'text':
      return <>{fontSize}{fontWeight}{textColor}{align}{marginTB}</>
    case 'image':
      return (
        <>
          <DimensionField label="Width (px or %)" value={style.width} onChange={v => set('width', v)} />
          {radius}
          {marginTB}
        </>
      )
    case 'button':
      return <>{bg}{textColor}{fontSize}{fontWeight}{padding}{radius}{align}</>
    case 'spacer':
      return <NumberField label="Height (px)" value={style.height} min={0} onChange={v => set('height', v)} />
    case 'divider':
      return (
        <>
          <ColorField label="Line color" value={style.color} onChange={v => set('color', v)} />
          {marginTB}
        </>
      )
    case 'navbar':
      return <>{bg}{textColor}{padding}</>
    case 'footer':
      return (
        <>
          {bg}
          {textColor}
          {align}
          <NumberField label="Padding top (px)" value={style.paddingTop} min={0} onChange={v => set('paddingTop', v)} />
          <NumberField label="Padding bottom (px)" value={style.paddingBottom} min={0} onChange={v => set('paddingBottom', v)} />
        </>
      )
    case 'form':
      return <>{bg}{padding}{radius}</>
    case 'collectionList':
      return <>{gap}{marginTB}</>
    default:
      return <div className="muted panel-hint">No style settings for this block.</div>
  }
}

/* ---------- panel shell ---------- */

export default function PropertiesPanel() {
  const tree = useEditorStore(s => s.tree)
  const selectedId = useEditorStore(s => s.selectedId)
  const duplicateBlock = useEditorStore(s => s.duplicateBlock)
  const removeBlock = useEditorStore(s => s.removeBlock)

  const node = selectedId ? findNode(tree, selectedId) : null
  if (!node || node.type === 'page') {
    return (
      <div className="ed-props">
        <div className="empty-state">Select a block to edit its properties</div>
      </div>
    )
  }

  const def = BLOCK_DEFINITIONS[node.type] || { label: node.type }
  return (
    <div className="ed-props">
      <div className="ed-side-title">{def.label}</div>
      <div className="props-section">
        <div className="props-section-title">Content</div>
        <ContentSection node={node} />
      </div>
      <div className="props-section">
        <div className="props-section-title">Style</div>
        <StyleSection node={node} />
      </div>
      <div className="props-footer">
        <div className="props-actions">
          <button type="button" className="btn btn-sm" onClick={() => duplicateBlock(node.id)}>Duplicate</button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => removeBlock(node.id)}>Delete</button>
        </div>
        <div className="mono muted">{node.type} · {node.id}</div>
      </div>
    </div>
  )
}
