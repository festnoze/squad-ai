// OWNED BY: frontend-editor agent.
// Renders a 1px horizontal rule; the style "color" key is the line color.
export default function DividerBlock({ node, css }) {
  const { color, ...rest } = css
  return <hr style={{ border: 'none', borderTop: '1px solid ' + (color || '#e5e7eb'), ...rest }} />
}
