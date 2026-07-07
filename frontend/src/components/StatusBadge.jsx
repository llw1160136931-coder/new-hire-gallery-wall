const STATUS_MAP = {
  pending: { label: '审核中', className: 'bg-amber-100 text-amber-700' },
  approved: { label: '已通过', className: 'bg-green-100 text-green-700' },
  rejected: { label: '已拒绝', className: 'bg-red-100 text-red-700' },
}

export default function StatusBadge({ status }) {
  const config = STATUS_MAP[status] || STATUS_MAP.pending
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  )
}
