// OWNED BY: frontend-editor agent.
// Renders the rich-ish HTML as-is in the editor canvas; the server renderer
// sanitizes to the whitelisted tags for preview/export.
export default function TextBlock({ node, css }) {
  return <div className="blk-text" style={css} dangerouslySetInnerHTML={{ __html: node.props.html || '' }} />
}
