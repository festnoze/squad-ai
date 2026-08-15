// OWNED BY: frontend-editor agent.
// Single source of truth for block types: labels, icons, containment rules,
// default props/style, and factory. Mirrors docs/decisions-editor.md section 1.3
// with the CONTRACTS.md reconciliations (collectionList props shape, limit 6).

import { nanoid } from 'nanoid'

const SECTION_CHILDREN = [
  'row', 'heading', 'text', 'image', 'button',
  'spacer', 'divider', 'form', 'collectionList',
]

export const BLOCK_DEFINITIONS = {
  page: {
    label: 'Page',
    icon: '▤',
    isContainer: true,
    acceptedChildren: ['section', 'navbar', 'footer'],
    defaultProps: {},
    defaultStyle: {},
  },
  section: {
    label: 'Section',
    icon: '▭',
    isContainer: true,
    acceptedChildren: SECTION_CHILDREN,
    defaultProps: {},
    defaultStyle: { paddingTop: 48, paddingBottom: 48, paddingLeft: 24, paddingRight: 24, backgroundColor: 'transparent' },
  },
  row: {
    label: 'Row',
    icon: '▥',
    isContainer: true,
    acceptedChildren: ['column'],
    defaultProps: {},
    defaultStyle: { gap: 24, paddingTop: 0, paddingBottom: 0 },
  },
  column: {
    label: 'Column',
    icon: '▯',
    isContainer: true,
    acceptedChildren: SECTION_CHILDREN,
    defaultProps: { widthFraction: 1 },
    defaultStyle: { paddingTop: 0, paddingRight: 0, paddingBottom: 0, paddingLeft: 0 },
  },
  heading: {
    label: 'Heading',
    icon: 'H',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { text: 'Heading', level: 2 },
    defaultStyle: { fontSize: 32, fontWeight: 700, textAlign: 'left', color: '#111111', marginBottom: 16 },
  },
  text: {
    label: 'Text',
    icon: '¶',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { html: '<p>Lorem ipsum dolor sit amet.</p>' },
    defaultStyle: { fontSize: 16, fontWeight: 400, textAlign: 'left', color: '#333333', marginBottom: 16 },
  },
  image: {
    label: 'Image',
    icon: '▣',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { src: '', alt: '' },
    defaultStyle: { width: '100%', borderRadius: 0, marginBottom: 16 },
  },
  button: {
    label: 'Button',
    icon: '▢',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { label: 'Click me', href: '#' },
    defaultStyle: { backgroundColor: '#2563eb', color: '#ffffff', fontSize: 16, fontWeight: 600, paddingTop: 12, paddingBottom: 12, paddingLeft: 24, paddingRight: 24, borderRadius: 6, textAlign: 'center' },
  },
  spacer: {
    label: 'Spacer',
    icon: '↕',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: {},
    defaultStyle: { height: 48 },
  },
  divider: {
    label: 'Divider',
    icon: '─',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: {},
    defaultStyle: { color: '#e5e7eb', marginTop: 16, marginBottom: 16 },
  },
  navbar: {
    label: 'Navbar',
    icon: '☰',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { brand: 'My Site', links: [{ label: 'Home', href: '/' }] },
    defaultStyle: { backgroundColor: '#ffffff', color: '#111111', paddingTop: 16, paddingBottom: 16, paddingLeft: 24, paddingRight: 24 },
  },
  footer: {
    label: 'Footer',
    icon: '▁',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { text: '(c) 2026 My Site' },
    defaultStyle: { backgroundColor: '#111111', color: '#ffffff', textAlign: 'center', paddingTop: 32, paddingBottom: 32 },
  },
  form: {
    label: 'Form',
    icon: '✎',
    isContainer: false,
    acceptedChildren: [],
    defaultProps: { title: 'Contact us', submitLabel: 'Send', fields: ['name', 'email', 'message'] },
    defaultStyle: { backgroundColor: '#f9fafb', paddingTop: 24, paddingBottom: 24, paddingLeft: 24, paddingRight: 24, borderRadius: 8 },
  },
  collectionList: {
    label: 'Collection list',
    icon: '≡',
    isContainer: false,
    acceptedChildren: [],
    // Props shape per CONTRACTS.md reconciliation #2: itemTemplate slots are
    // title/text/image (field keys or null); limit defaults to 6, clamped 1..50.
    defaultProps: { collectionId: null, limit: 6, itemTemplate: { title: null, text: null, image: null } },
    defaultStyle: { gap: 24, marginBottom: 16 },
  },
}

// Palette order (page and column are never offered from the palette).
export const PALETTE_TYPES = [
  'section', 'row', 'heading', 'text', 'image', 'button',
  'spacer', 'divider', 'navbar', 'footer', 'form', 'collectionList',
]

export function canDrop(containerType, childType) {
  const def = BLOCK_DEFINITIONS[containerType]
  return !!def && def.acceptedChildren.includes(childType)
}

export function createDefault(type) {
  const def = BLOCK_DEFINITIONS[type]
  if (!def) return null
  const node = {
    id: nanoid(10),
    type,
    props: JSON.parse(JSON.stringify(def.defaultProps)),
    style: { ...def.defaultStyle },
    children: [],
  }
  if (type === 'row') {
    node.children = [createDefault('column'), createDefault('column')]
  }
  return node
}
