// OWNED BY: frontend-editor agent.
export default function HeadingBlock({ node, css }) {
  const level = Math.min(4, Math.max(1, Number(node.props.level) || 2))
  const Tag = 'h' + level
  return <Tag style={css}>{node.props.text || ''}</Tag>
}
