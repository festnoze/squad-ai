import type { ItemStatus } from '../types/chat';

interface StatusBadgeProps {
  status: ItemStatus;
}

const STATUS_STYLES: Record<ItemStatus, { label: string; classes: string }> = {
  todo: {
    label: 'To Do',
    classes: 'bg-gray-200 text-gray-700',
  },
  in_progress: {
    label: 'In Progress',
    classes: 'bg-blue-600 text-white',
  },
  in_test: {
    label: 'In Test',
    classes: 'bg-yellow-400 text-gray-900',
  },
  done: {
    label: 'Done',
    classes: 'bg-green-600 text-white',
  },
  proposed: {
    label: 'Proposed',
    // purple-700 on white → contrast ratio ≈ 7.5:1, passes WCAG AA/AAA.
    classes: 'bg-purple-700 text-white',
  },
  blocked: {
    label: 'Blocked',
    // red-700 on white → strong contrast, signals a terminal failure.
    classes: 'bg-red-700 text-white',
  },
};

function StatusBadge({ status }: StatusBadgeProps) {
  const { label, classes } = STATUS_STYLES[status];
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${classes}`}
    >
      {label}
    </span>
  );
}

export default StatusBadge;
