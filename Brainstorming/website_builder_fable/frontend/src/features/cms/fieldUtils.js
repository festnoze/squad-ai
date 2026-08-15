// OWNED BY: frontend-cms agent (src/features/cms/**).
// Field helpers shared by the schema builder, entries table and entry form.

export const FIELD_TYPES = ['text', 'richtext', 'number', 'boolean', 'date', 'image', 'select']

export const KEY_REGEX = /^[a-z][a-z0-9_]*$/

// "Blog Posts" -> "blog-posts"
export function slugify(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

// "Cover Image" -> "cover_image" (must match [a-z][a-z0-9_]*)
export function keyFromLabel(label) {
  const key = String(label || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/^[0-9_]+/, '')
  return key
}

export function newField() {
  return { key: '', label: '', type: 'text', required: false, options: [] }
}

// Client-side mirror of the server field-descriptor rules.
// Returns [{index, message}] (empty = valid).
export function validateFields(fields) {
  const errors = []
  const seen = new Set()
  fields.forEach((field, index) => {
    if (!field.label || !field.label.trim()) {
      errors.push({ index, message: 'Label is required' })
    }
    if (!KEY_REGEX.test(field.key || '')) {
      errors.push({ index, message: 'Key must match [a-z][a-z0-9_]*' })
    } else if (seen.has(field.key)) {
      errors.push({ index, message: `Duplicate key "${field.key}"` })
    } else {
      seen.add(field.key)
    }
    if (!FIELD_TYPES.includes(field.type)) {
      errors.push({ index, message: 'Invalid type' })
    }
    if (field.type === 'select' && (!field.options || field.options.length === 0)) {
      errors.push({ index, message: 'Select needs at least one option' })
    }
  })
  return errors
}

export function stripTags(html) {
  return String(html || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

export function truncate(text, max = 80) {
  const s = String(text ?? '')
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

export function formatBytes(size) {
  if (size == null) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDate(iso) {
  if (!iso) return ''
  return String(iso).slice(0, 10)
}

// Resolve an image field value (asset id int or url string) to a URL using the
// project's asset map {id -> url}. Returns null when unresolvable.
export function resolveImageUrl(value, assetUrlById) {
  if (value == null || value === '') return null
  if (typeof value === 'number') return assetUrlById[value] || null
  return String(value)
}

// Default form value for a field type when the entry has null for it.
export function emptyValueFor(type) {
  switch (type) {
    case 'boolean':
      return false
    case 'number':
    case 'image':
      return null
    default:
      return ''
  }
}

// Normalize a form value into the JSON value sent to the API (null when empty).
export function toApiValue(type, value) {
  switch (type) {
    case 'text':
    case 'richtext':
    case 'date':
    case 'select':
      return value === '' || value == null ? null : String(value)
    case 'number': {
      if (value === '' || value == null) return null
      const num = Number(value)
      return Number.isNaN(num) ? null : num
    }
    case 'boolean':
      return Boolean(value)
    case 'image':
      return value === '' || value == null ? null : value
    default:
      return value ?? null
  }
}
