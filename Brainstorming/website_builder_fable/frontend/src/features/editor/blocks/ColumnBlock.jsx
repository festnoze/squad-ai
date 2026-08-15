// OWNED BY: frontend-editor agent.
// The flex weight (widthFraction) is applied on the BlockChrome wrapper (the
// actual flex child of the row); the inner container fills it.
import DropContainer from './DropContainer.jsx'

export default function ColumnBlock({ node, css, children }) {
  return (
    <DropContainer node={node} className="blk-column" style={{ height: '100%', ...css }}>
      {children}
    </DropContainer>
  )
}
