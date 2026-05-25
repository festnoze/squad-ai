import type { Item, ItemComplexity, ItemType } from '../../types/chat';
import StatusBadge from '../StatusBadge';

interface ItemTableProps {
  items: Item[];
  onRowClick?: (item: Item) => void;
  emptyMessage?: string;
}

const TYPE_LABELS: Record<ItemType, string> = {
  epic: 'Epic',
  user_story: 'User Story',
  task: 'Task',
};

const COMPLEXITY_STYLES: Record<
  ItemComplexity,
  { label: string; classes: string }
> = {
  simple: {
    label: 'simple',
    classes: 'bg-green-100 text-green-800',
  },
  medium: {
    label: 'medium',
    classes: 'bg-orange-100 text-orange-800',
  },
  complex: {
    label: 'complex',
    classes: 'bg-red-100 text-red-800',
  },
};

function truncateId(id: string): string {
  if (id.length <= 8) return id;
  return `${id.slice(0, 5)}...`;
}

function ItemTable({ items, onRowClick, emptyMessage }: ItemTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
        {emptyMessage ?? 'Aucun item'}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-gray-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="bg-gray-100 text-xs uppercase text-gray-600">
          <tr>
            <th className="px-4 py-3">Titre</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Complexite</th>
            <th className="px-4 py-3">Statut</th>
            <th className="px-4 py-3">Parent</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const complexityStyle = item.complexity
              ? COMPLEXITY_STYLES[item.complexity]
              : null;
            return (
              <tr
                key={item.id}
                onClick={() => onRowClick?.(item)}
                className="cursor-pointer border-t border-gray-100 hover:bg-gray-50"
              >
                <td className="px-4 py-3 font-medium text-gray-900">
                  {item.title}
                </td>
                <td className="px-4 py-3 italic uppercase text-gray-600">
                  {TYPE_LABELS[item.type]}
                </td>
                <td className="px-4 py-3">
                  {complexityStyle ? (
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${complexityStyle.classes}`}
                    >
                      {complexityStyle.label}
                    </span>
                  ) : (
                    <span className="text-gray-400">&mdash;</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={item.status} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">
                  {item.parent_id ? (
                    truncateId(item.parent_id)
                  ) : (
                    <span className="text-gray-400">&mdash;</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default ItemTable;
