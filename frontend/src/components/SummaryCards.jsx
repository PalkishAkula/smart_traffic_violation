const VIOLATION_COLORS = {
    NO_HELMET: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', icon: 'text-red-500' },
    TRIPLE_RIDING: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', icon: 'text-orange-500' },
    CO_RIDING_NO_HELMET: { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700', icon: 'text-purple-500' },
}

const DEFAULT_COLOR = { bg: 'bg-gray-50', border: 'border-gray-200', text: 'text-gray-700', icon: 'text-gray-500' }

const TYPE_LABELS = {
    NO_HELMET: 'No Helmet',
    TRIPLE_RIDING: 'Triple Riding',
    CO_RIDING_NO_HELMET: 'Co-rider No Helmet',
}

export default function SummaryCards({ summary, uniquePlates }) {
    const total = summary?.total || 0

    // Get all violation types dynamically (exclude 'total')
    const types = Object.keys(summary || {}).filter(k => k !== 'total')

    return (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Total Card */}
            <div className="bg-white rounded-2xl border border-gray-200 p-5">
                <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total</span>
                    <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                        <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                        </svg>
                    </div>
                </div>
                <p className="text-3xl font-bold text-gray-900">{total}</p>
                <p className="text-xs text-gray-400 mt-1">violations detected</p>
            </div>

            {/* Per-type cards */}
            {types.map((type) => {
                const colors = VIOLATION_COLORS[type] || DEFAULT_COLOR
                const count = summary[type] || 0
                const label = TYPE_LABELS[type] || type.replace(/_/g, ' ')
                return (
                    <div key={type} className={`${colors.bg} rounded-2xl border ${colors.border} p-5`}>
                        <div className="flex items-center justify-between mb-3">
                            <span className={`text-xs font-semibold ${colors.text} uppercase tracking-wider`}>
                                {label}
                            </span>
                        </div>
                        <p className={`text-3xl font-bold ${colors.text}`}>{count}</p>
                        <p className={`text-xs ${colors.text} opacity-60 mt-1`}>instance{count !== 1 ? 's' : ''}</p>
                    </div>
                )
            })}

            {/* Unique Plates Card */}
            <div className="bg-white rounded-2xl border border-gray-200 p-5">
                <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Plates</span>
                    <div className="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center">
                        <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                    </div>
                </div>
                <p className="text-3xl font-bold text-gray-900">{uniquePlates}</p>
                <p className="text-xs text-gray-400 mt-1">unique plates</p>
            </div>
        </div>
    )
}
