// OWNED BY: frontend-editor agent.
import DropContainer from './DropContainer.jsx'

export default function SectionBlock({ node, css, children }) {
  return (
    <DropContainer node={node} className="blk-section" style={css}>
      {children}
    </DropContainer>
  )
}
