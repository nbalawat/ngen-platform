import { cn } from '../../lib/utils';

const colorMap: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  healthy: 'bg-green-100 text-green-800',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  pending: 'bg-yellow-100 text-yellow-800',
  waiting_approval: 'bg-orange-100 text-orange-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-gray-100 text-gray-800',
  suspended: 'bg-red-100 text-red-800',
  registered: 'bg-blue-100 text-blue-800',
  offline: 'bg-gray-100 text-gray-800',
  block: 'bg-red-100 text-red-800',
  warn: 'bg-yellow-100 text-yellow-800',
  log: 'bg-gray-100 text-gray-800',
  escalate: 'bg-orange-100 text-orange-800',
  low: 'bg-gray-100 text-gray-700',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
  free: 'bg-gray-100 text-gray-700',
  standard: 'bg-blue-100 text-blue-800',
  enterprise: 'bg-purple-100 text-purple-800',
};

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  const colors = colorMap[value.toLowerCase()] || 'bg-gray-100 text-gray-700';
  return (
    <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', colors, className)}>
      {value.replace(/_/g, ' ')}
    </span>
  );
}
