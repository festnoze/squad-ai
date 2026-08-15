// OWNED BY: frontend-cms agent (src/features/cms/**).
// Minimal richtext widget: a contentEditable div with a small toolbar.
// Value is read/written as an HTML string. Uses document.execCommand
// (deprecated but universally supported; keeps the build dependency-free,
// per docs/decisions-cms.md 5.4).

import { useEffect, useRef } from 'react'

export default function RichTextEditor({ value, onChange }) {
  const editorRef = useRef(null)

  // Sync external value into the editor only when it differs (avoids caret jumps).
  useEffect(() => {
    const el = editorRef.current
    if (el && el.innerHTML !== (value || '')) {
      el.innerHTML = value || ''
    }
  }, [value])

  function exec(command) {
    editorRef.current?.focus()
    document.execCommand(command, false, null)
    emit()
  }

  function emit() {
    const el = editorRef.current
    if (el) onChange(el.innerHTML)
  }

  return (
    <div>
      <div className="richtext-toolbar">
        <button type="button" title="Bold" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('bold')}>
          <b>B</b>
        </button>
        <button type="button" title="Italic" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('italic')}>
          <i>I</i>
        </button>
        <button type="button" title="Bullet list" onMouseDown={(e) => e.preventDefault()} onClick={() => exec('insertUnorderedList')}>
          • List
        </button>
      </div>
      <div
        ref={editorRef}
        className="richtext-editor"
        contentEditable
        suppressContentEditableWarning
        onInput={emit}
        onBlur={emit}
      />
    </div>
  )
}
