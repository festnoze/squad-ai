// OWNED BY: frontend-editor agent.
import DropContainer from './DropContainer.jsx'

export default function RowBlock({ node, css, children }) {
  return (
    <DropContainer
      node={node}
      horizontal
      className="blk-row"
      style={{ display: 'flex', alignItems: 'stretch', ...css }}
    >
      {children}
    </DropContainer>
  )
}
