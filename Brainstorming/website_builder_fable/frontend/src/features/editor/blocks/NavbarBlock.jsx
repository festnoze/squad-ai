// OWNED BY: frontend-editor agent.
// Links render as spans in the editor so clicking never navigates away.
export default function NavbarBlock({ node, css }) {
  const links = Array.isArray(node.props.links) ? node.props.links : []
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', ...css }}>
      <strong>{node.props.brand || ''}</strong>
      <nav style={{ display: 'flex', gap: '16px' }}>
        {links.map((link, i) => (
          <span key={i} className="blk-navlink">{link.label}</span>
        ))}
      </nav>
    </div>
  )
}
