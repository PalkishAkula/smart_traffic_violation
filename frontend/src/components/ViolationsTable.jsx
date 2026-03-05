import { useState, useMemo } from 'react'

const VIOLATION_BADGE_STYLES = {
    NO_HELMET: 'bg-red-100 text-red-700',
    TRIPLE_RIDING: 'bg-orange-100 text-orange-700',
    CO_RIDING_NO_HELMET: 'bg-purple-100 text-purple-700',
}

const TYPE_LABELS = {
    NO_HELMET: 'No Helmet',
    TRIPLE_RIDING: 'Triple Riding',
    CO_RIDING_NO_HELMET: 'Co-rider No Helmet',
}

export default function ViolationsTable({ violations }) {
    const [sortField, setSortField] = useState('track_id')
    const [sortDir, setSortDir] = useState('asc')
    const [typeFilter, setTypeFilter] = useState('all')

    // Get unique violation types for filter dropdown
    const violationTypes = useMemo(() => {
        const types = new Set(violations.map(v => v.violation_type))
        return Array.from(types)
    }, [violations])

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
        } else {
            setSortField(field)
            setSortDir('asc')
        }
    }

    const filtered = useMemo(() => {
        let data = [...violations]
        if (typeFilter !== 'all') {
            data = data.filter(v => v.violation_type === typeFilter)
        }
        data.sort((a, b) => {
            const aVal = a[sortField]
            const bVal = b[sortField]
            if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
            if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
            return 0
        })
        return data
    }, [violations, typeFilter, sortField, sortDir])

    const SortIcon = ({ field }) => {
        if (sortField !== field) return <span className="text-gray-300 ml-1">↕</span>
        return <span className="text-blue-600 ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>
    }

    const violationBadge = (type) => {
        const style = VIOLATION_BADGE_STYLES[type] || 'bg-gray-100 text-gray-700'
        const label = TYPE_LABELS[type] || type.replace(/_/g, ' ')
        return (
            <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${style}`}>
                {label}
            </span>
        )
    }

    return (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-700">
                    Violations ({filtered.length})
                </h3>
                <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="all">All Types</option>
                    {violationTypes.map(type => (
                        <option key={type} value={type}>
                            {TYPE_LABELS[type] || type.replace(/_/g, ' ')}
                        </option>
                    ))}
                </select>
            </div>

            {/* Table */}
            {filtered.length === 0 ? (
                <div className="p-12 text-center text-sm text-gray-400">
                    No violations found
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th
                                    onClick={() => handleSort('track_id')}
                                    className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                                >
                                    Track ID <SortIcon field="track_id" />
                                </th>
                                <th
                                    onClick={() => handleSort('violation_type')}
                                    className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                                >
                                    Violation Type <SortIcon field="violation_type" />
                                </th>
                                <th
                                    onClick={() => handleSort('plate_text')}
                                    className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                                >
                                    Plate Number <SortIcon field="plate_text" />
                                </th>
                                <th
                                    onClick={() => handleSort('plate_conf')}
                                    className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                                >
                                    Confidence <SortIcon field="plate_conf" />
                                </th>
                                <th
                                    onClick={() => handleSort('frame_number')}
                                    className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                                >
                                    Frame <SortIcon field="frame_number" />
                                </th>
                                <th
                                    onClick={() => handleSort('plate_retries')}
                                    className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                                >
                                    Retries <SortIcon field="plate_retries" />
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((v, i) => (
                                <tr key={i} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                                    <td className="px-6 py-3.5 text-sm font-mono font-medium text-gray-900">
                                        #{v.track_id.toString().padStart(3, '0')}
                                    </td>
                                    <td className="px-6 py-3.5">
                                        {violationBadge(v.violation_type)}
                                    </td>
                                    <td className="px-6 py-3.5 text-sm">
                                        {v.plate_text ? (
                                            <span className="font-mono font-medium text-gray-900">{v.plate_text}</span>
                                        ) : (
                                            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-600">
                                                UNDETECTED
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-3.5 text-sm text-gray-600">
                                        {v.plate_text ? (
                                            <div className="flex items-center gap-2">
                                                <div className="w-16 bg-gray-200 rounded-full h-1.5">
                                                    <div
                                                        className="bg-blue-500 h-1.5 rounded-full"
                                                        style={{ width: `${v.plate_conf * 100}%` }}
                                                    />
                                                </div>
                                                <span className="text-xs font-medium">{(v.plate_conf * 100).toFixed(1)}%</span>
                                            </div>
                                        ) : (
                                            <span className="text-gray-400">—</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-3.5 text-sm font-mono text-gray-600">
                                        {v.frame_number}
                                    </td>
                                    <td className="px-6 py-3.5 text-sm text-gray-600">
                                        {v.plate_retries > 0 ? (
                                            <span className="text-amber-600 font-medium">{v.plate_retries}×</span>
                                        ) : (
                                            <span className="text-gray-400">0</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
