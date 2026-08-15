// OWNED BY: frontend-editor agent.
// Static contact form preview; the fixed field list is name/email/message.
export default function FormBlock({ node, css }) {
  const fields = Array.isArray(node.props.fields) && node.props.fields.length
    ? node.props.fields
    : ['name', 'email', 'message']
  return (
    <div style={css}>
      <h3 style={{ marginBottom: '12px' }}>{node.props.title || ''}</h3>
      {fields.map(field => (
        <div key={field} className="field">
          <label className="field-label" style={{ textTransform: 'capitalize' }}>{field}</label>
          {field === 'message'
            ? <textarea className="textarea" disabled placeholder={'Your ' + field} />
            : <input className="input" disabled placeholder={'Your ' + field} />}
        </div>
      ))}
      <span className="btn btn-primary" style={{ pointerEvents: 'none' }}>
        {node.props.submitLabel || 'Send'}
      </span>
    </div>
  )
}
