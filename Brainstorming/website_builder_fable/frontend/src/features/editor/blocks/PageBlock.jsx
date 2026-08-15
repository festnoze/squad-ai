// OWNED BY: frontend-editor agent.
import DropContainer from './DropContainer.jsx'

export default function PageBlock({ node, css, children }) {
  return (
    <DropContainer node={node} className="blk-page-body" style={css}>
      {children}
    </DropContainer>
  )
}
