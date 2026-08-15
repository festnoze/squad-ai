// OWNED BY: frontend-editor agent.
// Recursive renderer: maps each node type to its presentational component and
// wraps every non-root node in BlockChrome (selection, hover, drag, toolbar).
// Unknown types render a grey box so corrupt data never crashes the editor.

import BlockChrome from './BlockChrome.jsx'
import { toCss } from './styleUtils.js'
import PageBlock from './blocks/PageBlock.jsx'
import SectionBlock from './blocks/SectionBlock.jsx'
import RowBlock from './blocks/RowBlock.jsx'
import ColumnBlock from './blocks/ColumnBlock.jsx'
import HeadingBlock from './blocks/HeadingBlock.jsx'
import TextBlock from './blocks/TextBlock.jsx'
import ImageBlock from './blocks/ImageBlock.jsx'
import ButtonBlock from './blocks/ButtonBlock.jsx'
import SpacerBlock from './blocks/SpacerBlock.jsx'
import DividerBlock from './blocks/DividerBlock.jsx'
import NavbarBlock from './blocks/NavbarBlock.jsx'
import FooterBlock from './blocks/FooterBlock.jsx'
import FormBlock from './blocks/FormBlock.jsx'
import CollectionListBlock from './blocks/CollectionListBlock.jsx'

const COMPONENTS = {
  page: PageBlock,
  section: SectionBlock,
  row: RowBlock,
  column: ColumnBlock,
  heading: HeadingBlock,
  text: TextBlock,
  image: ImageBlock,
  button: ButtonBlock,
  spacer: SpacerBlock,
  divider: DividerBlock,
  navbar: NavbarBlock,
  footer: FooterBlock,
  form: FormBlock,
  collectionList: CollectionListBlock,
}

function UnknownBlock({ node }) {
  return <div className="blk-unknown">Unknown block: {node.type}</div>
}

export default function BlockRenderer({ node, parentId = null, index = 0 }) {
  const Comp = COMPONENTS[node.type] || UnknownBlock
  const rendered = (
    <Comp node={node} css={toCss(node.style)}>
      {(node.children || []).map((child, i) => (
        <BlockRenderer key={child.id} node={child} parentId={node.id} index={i} />
      ))}
    </Comp>
  )
  if (node.type === 'page') return rendered
  return (
    <BlockChrome node={node} parentId={parentId} index={index}>
      {rendered}
    </BlockChrome>
  )
}
