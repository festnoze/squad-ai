// OWNED BY: frontend-editor agent.
// textAlign positions the button within its parent; the rest styles the button
// itself. Rendered as a span so canvas clicks never navigate.
export default function ButtonBlock({ node, css }) {
  const { textAlign, ...buttonCss } = css
  return (
    <div style={{ textAlign: textAlign || 'left' }}>
      <span className="blk-button" style={{ display: 'inline-block', cursor: 'default', ...buttonCss }}>
        {node.props.label || 'Button'}
      </span>
    </div>
  )
}
