// OWNED BY: frontend-editor agent.
export default function ImageBlock({ node, css }) {
  if (!node.props.src) {
    return (
      <div className="blk-image-placeholder" style={css}>
        Image: choose a source in the properties panel
      </div>
    )
  }
  return (
    <img
      src={node.props.src}
      alt={node.props.alt || ''}
      draggable={false}
      style={{ display: 'block', maxWidth: '100%', ...css }}
    />
  )
}
