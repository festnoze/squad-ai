import { useLab } from '../store'
import type { ConfigSchema, FieldSchema } from '../types'

// ---------------------------------------------------------------------------
// Field grouping. We only render keys that actually exist in the schema, so
// adding/removing a SimConfig field never breaks the sidebar.
// `mode` is deliberately excluded — it lives in the Toolbar.
// ---------------------------------------------------------------------------

interface Section {
  title: string
  keys: string[]
}

const SECTIONS: Section[] = [
  {
    title: 'Population & simulation',
    keys: ['pop_size', 'sim_speed', 'seed', 'max_ticks_per_gen', 'stream_mode'],
  },
  {
    title: 'Réseau',
    keys: ['active_sensors', 'initial_hidden', 'max_nodes', 'max_connections', 'activation'],
  },
  {
    title: 'NEAT',
    keys: [
      'add_connection_rate',
      'add_node_rate',
      'weight_perturb_rate',
      'weight_replace_rate',
      'weight_sigma',
      'toggle_enable_rate',
      'compat_threshold',
      'c1',
      'c2',
      'c3',
      'elitism_per_species',
      'survival_threshold',
      'target_species',
    ],
  },
  {
    title: 'Apprentissage (gradient descent)',
    keys: ['gd_steps', 'gd_lr', 'teacher_k', 'gd_batch_size'],
  },
  {
    title: 'Confrontation NEAT vs GD',
    keys: ['gd_ratio', 'gd_teacher_scope'],
  },
]

// Keys we never auto-render in a generic section (mode is in the Toolbar).
const EXCLUDED_KEYS = new Set<string>(['mode'])

// Use a compact `.segmented` control instead of a <select> for these enums.
const SEGMENTED_ENUMS = new Set<string>(['stream_mode'])

// ---------------------------------------------------------------------------
// Pydantic v2 schema resolution helpers.
// ---------------------------------------------------------------------------

/** Get the `$defs` entry name from a `$ref` like "#/$defs/Mode". */
function refName(ref: unknown): string | null {
  if (typeof ref !== 'string') return null
  const m = ref.match(/#\/\$defs\/(.+)$/)
  return m ? m[1] : null
}

/** Resolve a property/items node to its `$defs` entry (following $ref / allOf[0].$ref). */
function resolveDef(
  node: unknown,
  schema: ConfigSchema,
): Record<string, any> | null {
  if (!node || typeof node !== 'object') return null
  const obj = node as Record<string, any>

  let name = refName(obj.$ref)
  if (!name && Array.isArray(obj.allOf) && obj.allOf.length > 0) {
    name = refName((obj.allOf[0] as Record<string, any>)?.$ref)
  }
  if (!name && Array.isArray(obj.anyOf)) {
    // anyOf may carry the ref alongside a null branch (Optional fields).
    for (const branch of obj.anyOf) {
      const n = refName((branch as Record<string, any>)?.$ref)
      if (n) {
        name = n
        break
      }
    }
  }
  if (!name) return null

  const defs = (schema.$defs as Record<string, any>) || {}
  return (defs[name] as Record<string, any>) || null
}

/**
 * Resolve a property to the list of enum string values it accepts, or null.
 * Handles direct `enum`, `$ref` → $defs, `allOf[0].$ref`, and `anyOf` branches.
 */
function resolveEnum(prop: FieldSchema, schema: ConfigSchema): string[] | null {
  if (Array.isArray(prop.enum)) return prop.enum.map((v) => String(v))
  const def = resolveDef(prop, schema)
  if (def && Array.isArray(def.enum)) return def.enum.map((v) => String(v))
  return null
}

/**
 * Resolve an array-of-enum property (e.g. `active_sensors`) to the enum values
 * available for its items. Returns null if the field isn't an array-of-enum.
 */
function resolveItemEnum(prop: FieldSchema, schema: ConfigSchema): string[] | null {
  const isArray =
    prop.type === 'array' || (Array.isArray(prop.type) && prop.type.includes('array'))
  if (!isArray || !prop.items) return null
  const items = prop.items as Record<string, any>
  if (Array.isArray(items.enum)) return items.enum.map((v) => String(v))
  const def = resolveDef(items, schema)
  if (def && Array.isArray(def.enum)) return def.enum.map((v) => String(v))
  return null
}

function isIntegerField(prop: FieldSchema): boolean {
  return prop.type === 'integer' || (Array.isArray(prop.type) && prop.type.includes('integer'))
}

function isNumericField(prop: FieldSchema): boolean {
  return (
    prop.type === 'number' ||
    prop.type === 'integer' ||
    (Array.isArray(prop.type) && (prop.type.includes('number') || prop.type.includes('integer')))
  )
}

function isBooleanField(prop: FieldSchema): boolean {
  return prop.type === 'boolean' || (Array.isArray(prop.type) && prop.type.includes('boolean'))
}

/** Effective minimum (Pydantic emits ge → minimum, gt → exclusiveMinimum). */
function fieldMin(prop: FieldSchema): number | undefined {
  if (typeof prop.minimum === 'number') return prop.minimum
  if (typeof (prop as any).exclusiveMinimum === 'number') return (prop as any).exclusiveMinimum
  return undefined
}

function fieldMax(prop: FieldSchema): number | undefined {
  if (typeof prop.maximum === 'number') return prop.maximum
  if (typeof (prop as any).exclusiveMaximum === 'number') return (prop as any).exclusiveMaximum
  return undefined
}

function titleFor(key: string, prop: FieldSchema): string {
  return prop.title || key
}

/** Format a numeric value compactly for the `.val` readout. */
function fmtNumber(value: unknown, isInt: boolean): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  if (isInt) return String(value)
  // Trim trailing zeros while keeping small floats readable.
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
}

// ---------------------------------------------------------------------------
// Individual control renderers.
// ---------------------------------------------------------------------------

interface ControlProps {
  fieldKey: string
  prop: FieldSchema
  schema: ConfigSchema
  value: unknown
  setField: (key: string, value: any) => void
}

function EnumControl({ fieldKey, prop, schema, value, setField }: ControlProps) {
  const options = resolveEnum(prop, schema) || []
  const current = value == null ? (prop.default as string | undefined) : String(value)
  const title = titleFor(fieldKey, prop)
  const useSegmented = SEGMENTED_ENUMS.has(fieldKey) && options.length > 0 && options.length <= 3

  return (
    <div className="field">
      <div className="field-label">
        <span>{title}</span>
        <span className="val">{current ?? '—'}</span>
      </div>
      {useSegmented ? (
        <div className="segmented">
          {options.map((opt) => (
            <button
              key={opt}
              className={current === opt ? 'active' : undefined}
              onClick={() => setField(fieldKey, opt)}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <select value={current ?? ''} onChange={(e) => setField(fieldKey, e.target.value)}>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      )}
      {prop.description && <div className="field-hint">{prop.description}</div>}
    </div>
  )
}

function MultiEnumControl({ fieldKey, prop, schema, value, setField }: ControlProps) {
  const options = resolveItemEnum(prop, schema) || []
  const selected: string[] = Array.isArray(value) ? value.map((v) => String(v)) : []
  const title = titleFor(fieldKey, prop)

  const toggle = (opt: string) => {
    const next = selected.includes(opt)
      ? selected.filter((v) => v !== opt)
      : [...selected, opt]
    setField(fieldKey, next)
  }

  return (
    <div className="field">
      <div className="field-label">
        <span>{title}</span>
        <span className="val">{selected.length}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {options.map((opt) => (
          <label
            key={opt}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
          >
            <input
              type="checkbox"
              checked={selected.includes(opt)}
              onChange={() => toggle(opt)}
            />
            <span style={{ fontSize: 13 }}>{opt}</span>
          </label>
        ))}
      </div>
      {prop.description && <div className="field-hint">{prop.description}</div>}
    </div>
  )
}

function NumberControl({ fieldKey, prop, value, setField }: ControlProps) {
  const isInt = isIntegerField(prop)
  const min = fieldMin(prop)
  const max = fieldMax(prop)
  const hasBounds = typeof min === 'number' && typeof max === 'number'
  const title = titleFor(fieldKey, prop)

  const numValue =
    typeof value === 'number'
      ? value
      : typeof prop.default === 'number'
        ? prop.default
        : undefined

  const step = isInt ? 1 : hasBounds ? Math.max((max! - min!) / 100, 0.0001) : 0.01

  const commit = (raw: string) => {
    if (raw === '') return
    const n = Number(raw)
    if (Number.isNaN(n)) return
    setField(fieldKey, n)
  }

  return (
    <div className="field">
      <div className="field-label">
        <span>{title}</span>
        <span className="val">{fmtNumber(numValue, isInt)}</span>
      </div>
      {hasBounds && (
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={numValue ?? min}
          onChange={(e) => commit(e.target.value)}
        />
      )}
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={numValue ?? ''}
        onChange={(e) => commit(e.target.value)}
        style={hasBounds ? { marginTop: 6 } : undefined}
      />
      {prop.description && <div className="field-hint">{prop.description}</div>}
    </div>
  )
}

function BooleanControl({ fieldKey, prop, value, setField }: ControlProps) {
  const checked =
    typeof value === 'boolean' ? value : Boolean(prop.default)
  const title = titleFor(fieldKey, prop)
  return (
    <div className="field">
      <div className="field-label">
        <span>{title}</span>
        <span className="val">{checked ? 'on' : 'off'}</span>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setField(fieldKey, e.target.checked)}
        />
        <span style={{ fontSize: 13 }}>{checked ? 'Activé' : 'Désactivé'}</span>
      </label>
      {prop.description && <div className="field-hint">{prop.description}</div>}
    </div>
  )
}

/** Pick the right control for a field based on its resolved schema kind. */
function FieldControl(props: ControlProps) {
  const { prop, schema } = props

  // array-of-enum (e.g. active_sensors)
  if (resolveItemEnum(prop, schema)) {
    return <MultiEnumControl {...props} />
  }
  // single enum (via direct enum, $ref, allOf, or anyOf)
  if (resolveEnum(prop, schema)) {
    return <EnumControl {...props} />
  }
  if (isBooleanField(prop)) {
    return <BooleanControl {...props} />
  }
  if (isNumericField(prop)) {
    return <NumberControl {...props} />
  }
  // Unknown kind: fall back to a permissive text input so nothing is lost.
  const title = titleFor(props.fieldKey, prop)
  return (
    <div className="field">
      <div className="field-label">
        <span>{title}</span>
      </div>
      <input
        type="text"
        value={props.value == null ? '' : String(props.value)}
        onChange={(e) => props.setField(props.fieldKey, e.target.value)}
      />
      {prop.description && <div className="field-hint">{prop.description}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sidebar.
// ---------------------------------------------------------------------------

export function Sidebar() {
  const schema = useLab((s) => s.schema)
  const dirty = useLab((s) => s.dirty)
  const applying = useLab((s) => s.applying)
  const setField = useLab((s) => s.setField)
  const resetDraft = useLab((s) => s.resetDraft)
  const applyConfig = useLab((s) => s.applyConfig)
  // Subscribe to config + draft directly so the panel re-renders when the
  // server echoes its config and when local edits change (effectiveConfig() is
  // a stable function reference and would not trigger re-renders on its own).
  const config = useLab((s) => s.config)
  const draft = useLab((s) => s.draft)

  if (!schema) {
    return <div className="empty-hint">Chargement du schéma…</div>
  }

  const properties = schema.properties || {}
  const effective = { ...config, ...draft }

  // Current value for a control: live draft/config override, else schema default.
  const valueFor = (key: string): unknown => {
    const v = effective[key]
    return v === undefined ? properties[key]?.default : v
  }

  // Build the ordered section list, dropping keys absent from the schema.
  const placed = new Set<string>(EXCLUDED_KEYS)
  const sections = SECTIONS.map((sec) => {
    const keys = sec.keys.filter((k) => {
      if (!(k in properties)) return false
      placed.add(k)
      return true
    })
    return { title: sec.title, keys }
  }).filter((sec) => sec.keys.length > 0)

  // Anything in the schema we didn't explicitly place goes under "Autres".
  const leftovers = Object.keys(properties).filter((k) => !placed.has(k))
  if (leftovers.length > 0) {
    sections.push({ title: 'Autres', keys: leftovers })
  }

  const renderField = (key: string) => {
    const prop = properties[key]
    if (!prop) return null
    return (
      <FieldControl
        key={key}
        fieldKey={key}
        prop={prop}
        schema={schema}
        value={valueFor(key)}
        setField={setField}
      />
    )
  }

  return (
    <div className="sidebar-inner">
      <h3>Configuration</h3>
      <div className="field-hint" style={{ marginTop: 6, marginBottom: 4 }}>
        Les changements structurels (taille de population, capteurs, seed, plafonds de
        complexité) s'appliquent au prochain reset.
      </div>

      {sections.map((sec) => (
        <div key={sec.title}>
          <div className="section-title">{sec.title}</div>
          {sec.keys.map(renderField)}
        </div>
      ))}

      <div className="sidebar-footer" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
        {(dirty || applying) && (
          <div className="dirty-flag" style={{ marginLeft: 0, marginBottom: 8 }}>
            {applying ? (
              <>
                <span className="spinner" /> Application en cours…
              </>
            ) : (
              <>● modifications non appliquées</>
            )}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn primary"
            disabled={!dirty || applying}
            onClick={applyConfig}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            {applying ? <span className="spinner" /> : 'Appliquer'}
          </button>
          <button
            className="btn ghost"
            disabled={!dirty || applying}
            onClick={resetDraft}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            Réinitialiser
          </button>
        </div>
      </div>
    </div>
  )
}
