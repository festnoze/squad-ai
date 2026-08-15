// OWNED BY: frontend-editor agent.
// Maps stored block style (camelCase keys, numbers mean px) to React inline CSS.

const NON_PX_NUMERIC_KEYS = new Set(['fontWeight'])

export function toCss(style) {
  const out = {}
  for (const [key, value] of Object.entries(style || {})) {
    if (value === null || value === undefined || value === '') continue
    if (typeof value === 'number' && !NON_PX_NUMERIC_KEYS.has(key)) {
      out[key] = value + 'px'
    } else {
      out[key] = value
    }
  }
  return out
}
