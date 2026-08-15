# Website Builder Fable - WYSIWYG Editor Architecture

Decision document for the page editor. Later agents implement this design as written. Frontend stack: React 18 + Vite (port 5300), zustand, @dnd-kit/core + @dnd-kit/sortable, nanoid. All API calls go through the Vite proxy `/api -> http://localhost:8300`.

Decisions taken by this agent (open questions in the spec resolved here):
- `spacer` and `divider` are two distinct block types (simplest palette and renderer mapping).
- `row` children are `column` blocks (a dedicated `column` type; the palette exposes "Row" which inserts a row pre-filled with 2 columns).
- Autosave only (no explicit save button); debounced 1500 ms PUT, with a "Saving... / Saved" indicator driven by the dirty flag.
- Single selection only (no multi-select), per spec.
- Undo/redo history is snapshot-based (full tree copies), capped at 50 entries. Simplest correct approach for local-first single-user trees of this size.
- IDs are `nanoid(10)` strings generated client-side at insertion time.

---

## 1. Block tree JSON schema

A page's `content` column stores one JSON document: a single root node of type `page`.

### 1.1 Node shape

Every node has exactly these five keys (all always present when serialized):

```json
{
  "id": "string (nanoid, unique within the page)",
  "type": "string (one of the block types below)",
  "props": { "content fields, type-specific" },
  "style": { "visual fields, subset of the allowed style keys" },
  "children": [ "array of nodes; [] for leaf types" ]
}
```

TypeScript definition (put in `frontend/src/editor/types.ts`):

```ts
export interface BlockNode {
  id: string;
  type: BlockType;
  props: Record<string, unknown>;
  style: Record<string, string | number>;
  children: BlockNode[];
}

export type BlockType =
  | "page" | "section" | "row" | "column"
  | "heading" | "text" | "image" | "button"
  | "spacer" | "divider" | "navbar" | "footer"
  | "form" | "collectionList";
```

### 1.2 Allowed style keys (global vocabulary)

Style values are stored camelCased and map 1:1 to inline CSS (see section 5.3). Only these keys are ever written:

`paddingTop, paddingRight, paddingBottom, paddingLeft, marginTop, marginRight, marginBottom, marginLeft, color, backgroundColor, fontSize, fontWeight, textAlign, width, maxWidth, height, borderRadius, gap`

Numbers mean pixels (converted to `"12px"` at render time); strings are passed through (`"100%"`, `"#ff0000"`, `"center"`).

### 1.3 Block types, default props, default style

The single source of truth in code is `frontend/src/editor/blockDefinitions.ts` exporting `BLOCK_DEFINITIONS: Record<BlockType, BlockDefinition>` with `{ label, icon, isContainer, acceptedChildren, defaultProps, defaultStyle, createDefault() }`. Contents:

| type | container | default props | default style |
|---|---|---|---|
| `page` | yes (root only, never in palette) | `{}` | `{}` |
| `section` | yes | `{}` | `{ paddingTop: 48, paddingBottom: 48, paddingLeft: 24, paddingRight: 24, backgroundColor: "transparent" }` |
| `row` | yes (columns only) | `{}` | `{ gap: 24, paddingTop: 0, paddingBottom: 0 }` |
| `column` | yes | `{ widthFraction: 1 }` (relative flex-grow weight) | `{ paddingTop: 0, paddingRight: 0, paddingBottom: 0, paddingLeft: 0 }` |
| `heading` | no | `{ text: "Heading", level: 2 }` (level 1-4) | `{ fontSize: 32, fontWeight: 700, textAlign: "left", color: "#111111", marginBottom: 16 }` |
| `text` | no | `{ html: "<p>Lorem ipsum dolor sit amet.</p>" }` (rich-ish: sanitized subset b/i/u/a/p/br/ul/ol/li) | `{ fontSize: 16, fontWeight: 400, textAlign: "left", color: "#333333", marginBottom: 16 }` |
| `image` | no | `{ src: "", alt: "" }` (src is an asset URL `/api/projects/{pid}/assets/{file}` or external) | `{ width: "100%", borderRadius: 0, marginBottom: 16 }` |
| `button` | no | `{ label: "Click me", href: "#" }` | `{ backgroundColor: "#2563eb", color: "#ffffff", fontSize: 16, fontWeight: 600, paddingTop: 12, paddingBottom: 12, paddingLeft: 24, paddingRight: 24, borderRadius: 6, textAlign: "center" }` |
| `spacer` | no | `{}` | `{ height: 48 }` |
| `divider` | no | `{}` | `{ color: "#e5e7eb", marginTop: 16, marginBottom: 16 }` (renders 1px hr, color = border color) |
| `navbar` | no | `{ brand: "My Site", links: [{ label: "Home", href: "/" }] }` | `{ backgroundColor: "#ffffff", color: "#111111", paddingTop: 16, paddingBottom: 16, paddingLeft: 24, paddingRight: 24 }` |
| `footer` | no | `{ text: "(c) 2026 My Site" }` | `{ backgroundColor: "#111111", color: "#ffffff", textAlign: "center", paddingTop: 32, paddingBottom: 32 }` |
| `form` | no | `{ title: "Contact us", submitLabel: "Send", fields: ["name", "email", "message"] }` (fields list is fixed per spec, not editable) | `{ backgroundColor: "#f9fafb", paddingTop: 24, paddingBottom: 24, paddingLeft: 24, paddingRight: 24, borderRadius: 8 }` |
| `collectionList` | no | `{ collectionId: null, itemTemplate: { titleField: "", textField: "", imageField: "" }, limit: 10 }` | `{ gap: 24, marginBottom: 16 }` |

`createDefault()` returns a fresh node with a new nanoid, deep-copied defaults, and for `row` two pre-created `column` children. A new page's content is:

```json
{ "id": "root", "type": "page", "props": {}, "style": {}, "children": [] }
```

The root `page` node id is always the literal string `"root"`; it is never selectable, draggable, or deletable.

---

## 2. Selection model

Single selection, stored as `selectedId: string | null` in the zustand store (section 4).

- **Click on canvas**: every rendered block wrapper calls `e.stopPropagation(); select(node.id)` on `onClick`. stopPropagation guarantees the innermost block under the cursor wins. Clicking canvas background (the page root wrapper) calls `select(null)`.
- **Selection outline**: the selected block wrapper gets class `blk-selected` (2px solid `#2563eb` outline via CSS `outline`, so layout is unaffected). Hovered blocks get a 1px dashed outline `blk-hover`.
- **Breadcrumb of ancestors**: a bar under the editor toolbar. Compute the ancestor chain with `findPath(tree, selectedId)` (returns nodes from root to selected). Render one clickable chip per ancestor (skip the `page` root, label it "Page" as the first chip that selects null) plus the selected block's label. Clicking a chip calls `select(thatId)`.
- **Escape**: clears selection (`select(null)`).
- **Delete / Backspace**: removes the selected block (`removeBlock(selectedId)`), then selection becomes null.
- **Ctrl+D**: duplicates the selected block (`duplicateBlock(selectedId)`): deep-clone with fresh nanoids for the clone and all its descendants, insert immediately after the original in the same parent, select the clone. Call `e.preventDefault()` to suppress the browser bookmark dialog.
- Keyboard handling: one `keydown` listener registered in `EditorPage` via `useEffect` on `window`. It ignores events when `document.activeElement` is an `input`, `textarea`, `select`, or `[contenteditable]` element (so typing in the properties panel or inline text never deletes blocks). Ctrl+Z / Ctrl+Shift+Z (and Ctrl+Y) map to undo/redo in the same listener.

Tree helpers (pure functions in `frontend/src/editor/treeUtils.ts`, all return new trees, never mutate): `findNode(tree, id)`, `findParent(tree, id)`, `findPath(tree, id)`, `insertNode(tree, parentId, index, node)`, `removeNode(tree, id)`, `moveNode(tree, id, newParentId, newIndex)`, `updateNode(tree, id, patch)`, `cloneWithNewIds(node)`.

---

## 3. Drag and drop (@dnd-kit)

Packages: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`. One `<DndContext>` wraps palette + canvas in `EditorPage`. Collision detection: `closestCenter`. Sensors: `PointerSensor` with `activationConstraint: { distance: 5 }` (so plain clicks still select instead of starting a drag).

### 3.1 Draggable sources

- **Palette items**: `useDraggable` with `id: "palette-" + blockType` and `data: { kind: "palette", blockType }`. Dragging never removes the palette item; on valid drop a new node is created via `BLOCK_DEFINITIONS[blockType].createDefault()`.
- **Canvas blocks**: each block wrapper (except root) is registered with `useSortable` (`id: node.id`, `data: { kind: "canvas", nodeId: node.id, parentId, index, type: node.type }`). The drag handle is a small grip icon shown in the block's floating toolbar on hover/selection; `listeners` are attached to the handle only, so inline interactions stay usable.

### 3.2 Droppable containers

Each container block renders its children inside a `<SortableContext items={children.map(c => c.id)} strategy={verticalListSortingStrategy}>` (`horizontalListSortingStrategy` for `row`). Additionally each container registers a `useDroppable` zone (`id: "container-" + node.id`, `data: { kind: "container", nodeId: node.id }`) covering its body, so empty containers can receive drops (empty containers render a 48px min-height dashed placeholder reading "Drop blocks here").

### 3.3 Acceptance rules (who accepts which children)

Defined declaratively in `blockDefinitions.ts` as `acceptedChildren`:

| container | accepts |
|---|---|
| `page` (root canvas) | `section`, `navbar`, `footer` only |
| `section` | everything except `page`, `section`, `column`, `navbar`, `footer` (i.e. `row, heading, text, image, button, spacer, divider, form, collectionList`) |
| `row` | `column` only (columns are added/removed via the properties panel "Columns" stepper, not via palette) |
| `column` | same set as `section` minus `row` is ALLOWED (nested rows permitted once): accepts `row, heading, text, image, button, spacer, divider, form, collectionList` |
| all other types | leaf, accept nothing |

Helper: `canDrop(containerType: BlockType, childType: BlockType): boolean` reads `acceptedChildren`. It is enforced in `onDragOver`/`onDragEnd`; invalid targets show no drop indicator and drops there are no-ops. An additional guard rejects dropping a node into its own descendant (`isDescendant(tree, dragId, targetId)`).

### 3.4 Drop resolution (onDragEnd)

Implemented in `frontend/src/editor/useEditorDnd.ts`:

1. Read `active.data.current` and `over`. If `over` is null, do nothing.
2. Resolve target `(parentId, index)`:
   - If `over.data.kind === "container"`: parent = that container, index = `children.length` (append).
   - If `over` is a sortable block: parent = that block's parentId, index = that block's index (dnd-kit sortable gives before/after via `arrayMove` semantics; compute final index from `over` index and whether the pointer is past the midpoint - use the index dnd-kit reports).
3. Validate with `canDrop(parentType, draggedType)` and the descendant guard; bail silently if invalid.
4. Palette drag: `store.insertBlock(parentId, index, createDefault(blockType))`, then select the new node.
5. Canvas drag: same parent -> `store.moveBlock(id, parentId, newIndex)` (internally `arrayMove`); cross-parent -> same action (remove from old parent, insert into new).
6. Every successful drop pushes one undo snapshot and marks dirty.

`<DragOverlay>` renders a compact chip (block icon + label) while dragging, both for palette and canvas drags; the original canvas block gets `opacity: 0.4` while active.

---

## 4. State management (zustand)

Single store in `frontend/src/editor/editorStore.ts`, created with `create<EditorState>()(...)`. No middleware needed except `immer` is NOT used - tree utils already return new trees.

### 4.1 Store shape

```ts
interface EditorState {
  // data
  projectId: string | null;
  pageId: string | null;
  tree: BlockNode;                 // root page node
  selectedId: string | null;
  // history
  past: BlockNode[];               // undo stack, max 50, oldest dropped
  future: BlockNode[];             // redo stack
  // persistence
  dirty: boolean;
  saving: boolean;
  lastSavedAt: string | null;      // ISO string for the "Saved" indicator
  // ui
  device: "desktop" | "tablet" | "mobile";

  // actions (exact names)
  loadPage(projectId: string, pageId: string): Promise<void>;
  select(id: string | null): void;
  insertBlock(parentId: string, index: number, node: BlockNode): void;
  removeBlock(id: string): void;
  moveBlock(id: string, newParentId: string, newIndex: number): void;
  duplicateBlock(id: string): void;
  updateBlockProps(id: string, patch: Record<string, unknown>): void;
  updateBlockStyle(id: string, patch: Record<string, string | number>): void;
  undo(): void;
  redo(): void;
  setDevice(d: "desktop" | "tablet" | "mobile"): void;
  savePage(): Promise<void>;       // immediate PUT, used by flush
  markSaved(): void;               // internal
}
```

### 4.2 Mutation pattern

Every tree-mutating action (`insertBlock`, `removeBlock`, `moveBlock`, `duplicateBlock`, `updateBlockProps`, `updateBlockStyle`) goes through one internal helper:

```ts
function commit(nextTree: BlockNode) {
  set(s => ({
    tree: nextTree,
    past: [...s.past.slice(-49), s.tree],
    future: [],
    dirty: true,
  }));
  scheduleAutosave();
}
```

Exception to avoid history spam: `updateBlockProps`/`updateBlockStyle` calls coming from continuous inputs (color picker drag, text typing) are coalesced - the properties panel commits onChange for live preview but the store only pushes a history snapshot if more than 800 ms elapsed since the previous push for the same `(id, firstKeyOfPatch)`; otherwise it replaces the tree without pushing to `past`. Implement as a module-level `lastPushRef` in the store file.

`undo()`: pop last of `past` into `tree`, push current tree onto `future`, set `dirty: true`, clear `selectedId` if the selected node no longer exists, `scheduleAutosave()`. `redo()` is symmetric. History is in-memory only, reset on `loadPage`.

### 4.3 Autosave

- `scheduleAutosave` is a module-level debounce (plain `setTimeout`, 1500 ms): each call clears the previous timer; on fire it calls `get().savePage()`.
- `savePage()`: if not dirty, return. Set `saving: true`, then
  `PUT /api/projects/{projectId}/pages/{pageId}` with body `{ "content": tree }` (JSON). On 2xx: `set({ dirty: false, saving: false, lastSavedAt: new Date().toISOString() })`. On failure: `saving: false`, keep `dirty: true`, retry automatically on the next mutation (and show a red "Save failed - retrying on next change" note in the toolbar). No optimistic locking (single user).
- Flush on exit: `EditorPage` registers a `beforeunload` handler and an unmount cleanup that call `savePage()` immediately if dirty.
- Toolbar indicator: `saving ? "Saving..." : dirty ? "Unsaved changes" : "Saved"`.

Selectors: components subscribe narrowly (`useEditorStore(s => s.selectedId)` etc.) to avoid full-canvas re-renders; the canvas subscribes to `tree`.

---

## 5. Rendering

### 5.1 BlockRenderer (recursive)

`frontend/src/editor/BlockRenderer.tsx`:

```tsx
const COMPONENTS: Record<BlockType, React.FC<BlockComponentProps>> = {
  page: PageBlock, section: SectionBlock, row: RowBlock, column: ColumnBlock,
  heading: HeadingBlock, text: TextBlock, image: ImageBlock, button: ButtonBlock,
  spacer: SpacerBlock, divider: DividerBlock, navbar: NavbarBlock,
  footer: FooterBlock, form: FormBlock, collectionList: CollectionListBlock,
};

function BlockRenderer({ node }: { node: BlockNode }) {
  const Comp = COMPONENTS[node.type] ?? UnknownBlock;
  return (
    <BlockChrome node={node}>
      <Comp node={node} style={toCss(node.style)}>
        {node.children.map(c => <BlockRenderer key={c.id} node={c} />)}
      </Comp>
    </BlockChrome>
  );
}
```

Container components (`SectionBlock`, `RowBlock`, `ColumnBlock`, `PageBlock`) wrap `children` in their `SortableContext` + droppable zone. Leaf components ignore `children`. `UnknownBlock` renders a grey "Unknown block: {type}" box so corrupt data never crashes the editor.

### 5.2 BlockChrome (edit-mode wrapper)

`BlockChrome` provides all editor affordances so block components stay presentational:

- `useSortable` registration (skipped for `type === "page"`).
- Click-to-select (`onClick` with stopPropagation), hover outline, selected outline.
- Floating mini-toolbar on the selected block (top-right, absolutely positioned): block label, drag grip (dnd listeners attached here), duplicate button, delete button.
- Renders as `<div style={{ position: "relative" }}>` around the block; the block's own `style` CSS is applied to the inner component element, not the chrome, so outlines never fight block backgrounds.

Preview (the server-rendered HTML route) does not use React at all per spec (backend renders HTML+CSS), so no `editable` prop plumbing is needed: `BlockRenderer` is always edit mode.

### 5.3 Style mapping

`toCss(style)` in `frontend/src/editor/styleUtils.ts` converts stored style to `React.CSSProperties`: numeric values for the pixel keys (`padding*, margin*, fontSize, borderRadius, gap, height`) become `"{n}px"`; strings pass through; keys copy 1:1 since names already match CSS camelCase. `gap` only applies to `row` and `collectionList` (their components use flex). `row` renders `display: flex`; each `column` gets `flex: {widthFraction} 1 0`.

### 5.4 Responsive preview

Implemented purely by constraining canvas width. Store field `device` with widths:

```ts
const DEVICE_WIDTHS = { desktop: 1200, tablet: 768, mobile: 375 } as const;
```

The editor layout is: left palette (fixed 240px) | center canvas area (grey `#e5e7eb` background, scrollable) | right properties panel (fixed 300px). The canvas is a centered white sheet: `width: DEVICE_WIDTHS[device]px; margin: 24px auto; min-height: 80vh; background: white; box-shadow: 0 1px 4px rgba(0,0,0,.15)`. Toolbar has three toggle buttons (Desktop / Tablet / Mobile) calling `setDevice`. Switching device changes only the sheet width (no per-device styles are stored - blocks reflow via their normal CSS, e.g. `width: 100%` images).

---

## 6. Properties panel

`frontend/src/editor/PropertiesPanel.tsx`. When `selectedId` is null it shows "Select a block to edit its properties". Otherwise two sections: **Content** (writes via `updateBlockProps`) and **Style** (writes via `updateBlockStyle`). All style edits map directly to inline CSS through the section 5.3 pipeline.

Reusable style field widgets: `SpacingGroup` (4 number inputs for padding or margin, px), `ColorField` (`<input type="color">` + hex text input), `NumberField` (px), `SelectField`, `AlignField` (left/center/right button group), `TextField`.

Per-type field matrix:

| type | Content fields | Style fields |
|---|---|---|
| `section` | (none) | padding (4), margin top/bottom, backgroundColor, borderRadius, maxWidth |
| `row` | "Columns" stepper (1-4: adds default columns at end / removes from end, refuses removal of non-empty column) | gap, padding (4), backgroundColor |
| `column` | widthFraction (number 1-12, relative weight) | padding (4), backgroundColor, borderRadius |
| `heading` | text (text input), level (select H1-H4) | fontSize, fontWeight (select 400/500/600/700/800), color, textAlign, margin top/bottom |
| `text` | html (textarea with a tiny toolbar for bold/italic/link, or raw HTML textarea - implementer choice, textarea acceptable) | fontSize, fontWeight, color, textAlign, margin top/bottom |
| `image` | src (text input + "Choose from assets" button opening the AssetPicker), alt (text) | width (text: px or %), borderRadius, margin top/bottom |
| `button` | label (text), href (text) | backgroundColor, color, fontSize, fontWeight, padding (4), borderRadius, textAlign (of the button within its parent) |
| `spacer` | (none) | height |
| `divider` | (none) | color (line color), margin top/bottom |
| `navbar` | brand (text), links (repeatable list: label + href rows, add/remove) | backgroundColor, color, padding (4) |
| `footer` | text (textarea) | backgroundColor, color, textAlign, padding top/bottom |
| `form` | title (text), submitLabel (text) (field list fixed: name/email/message, shown read-only) | backgroundColor, padding (4), borderRadius |
| `collectionList` | collectionId (select fed by `GET /api/projects/{pid}/collections`), titleField / textField / imageField (selects fed by the chosen collection's schema), limit (number) | gap, margin top/bottom |

Panel footer for every block: Duplicate and Delete buttons (same actions as keyboard), plus the block type label and id (small, monospace, aids debugging).

---

## 7. File map (frontend, for the implementing agents)

```
frontend/src/editor/
  types.ts               BlockNode, BlockType, DeviceKind
  blockDefinitions.ts    BLOCK_DEFINITIONS (labels, defaults, acceptedChildren, createDefault)
  treeUtils.ts           pure tree operations (find/insert/remove/move/update/clone)
  styleUtils.ts          toCss()
  editorStore.ts         zustand store + autosave debounce
  useEditorDnd.ts        DndContext handlers (onDragStart/Over/End), canDrop
  EditorPage.tsx         layout, DndContext, keyboard shortcuts, toolbar, breadcrumb
  Palette.tsx            draggable palette items
  Canvas.tsx             device-width sheet + <BlockRenderer node={tree} />
  BlockRenderer.tsx      recursive renderer + COMPONENTS map
  BlockChrome.tsx        selection/hover/drag wrapper + mini-toolbar
  blocks/                one presentational component per block type
  PropertiesPanel.tsx    content + style editors per the section 6 matrix
```

Rules reminder for implementers: no em-dash character anywhere; Windows-friendly non-interactive commands; page content persists exactly the JSON of section 1 (the backend stores it opaquely and the server-side preview renderer consumes the same schema).
