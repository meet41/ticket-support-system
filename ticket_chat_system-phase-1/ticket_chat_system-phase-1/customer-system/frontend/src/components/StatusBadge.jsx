const statusStyles = {
  open: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  resolved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300',
  closed: 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const priorityStyles = {
  high: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  low: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300',
};

export function StatusBadge({ status }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${statusStyles[status] || statusStyles.open}`}>
      {(status || '').replace('_', ' ')}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${priorityStyles[priority] || priorityStyles.low}`}>
      {priority}
    </span>
  );
}
