// OWNED BY: frontend-editor agent.
export default function FooterBlock({ node, css }) {
  return <div style={css}>{node.props.text || ''}</div>
}
