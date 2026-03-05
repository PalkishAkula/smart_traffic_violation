export default function StatCard({ title, value, subtitle, icon, color = 'blue' }) {
    const colorMap = {
        blue: { bg: 'bg-blue-50', icon: 'bg-blue-100 text-blue-600', text: 'text-blue-700' },
        red: { bg: 'bg-red-50', icon: 'bg-red-100 text-red-600', text: 'text-red-700' },
        orange: { bg: 'bg-orange-50', icon: 'bg-orange-100 text-orange-600', text: 'text-orange-700' },
        purple: { bg: 'bg-purple-50', icon: 'bg-purple-100 text-purple-600', text: 'text-purple-700' },
        green: { bg: 'bg-green-50', icon: 'bg-green-100 text-green-600', text: 'text-green-700' },
    }

    const c = colorMap[color] || colorMap.blue

    return (
        <div className="bg-white rounded-2xl border border-gray-200 p-5 hover:shadow-sm transition-shadow">
            <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    {title}
                </span>
                {icon && (
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${c.icon}`}>
                        {icon}
                    </div>
                )}
            </div>
            <p className={`text-3xl font-bold ${c.text}`}>{value}</p>
            {subtitle && (
                <p className="text-xs text-gray-400 mt-1">{subtitle}</p>
            )}
        </div>
    )
}
