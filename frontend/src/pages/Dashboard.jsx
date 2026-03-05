import { useState, useEffect } from 'react'
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell
} from 'recharts'
import { AlertTriangle, Camera, Shield, TrendingUp } from 'lucide-react'
import api from '../services/api'
import StatCard from '../components/StatCard'
import ViolationTable from '../components/ViolationTable'
import EvidenceModal from '../components/EvidenceModal'

const PIE_COLORS = {
    NO_HELMET: '#ef4444',
    TRIPLE_RIDING: '#f97316',
    CO_RIDING_NO_HELMET: '#a855f7',
}

export default function Dashboard() {
    const [summary, setSummary] = useState(null)
    const [timeline, setTimeline] = useState([])
    const [selectedViolation, setSelectedViolation] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchData()
    }, [])

    const fetchData = async () => {
        try {
            const [sumRes, timeRes] = await Promise.all([
                api.get('/api/stats/summary'),
                api.get('/api/stats/timeline?days=7'),
            ])
            setSummary(sumRes.data)
            setTimeline(timeRes.data.data || [])
        } catch (err) {
            console.error('Failed to load dashboard:', err)
        } finally {
            setLoading(false)
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            </div>
        )
    }

    const pieData = summary?.by_type
        ? Object.entries(summary.by_type).map(([name, value]) => ({ name, value }))
        : []

    // Most common violation
    const mostCommon = pieData.length > 0
        ? pieData.reduce((a, b) => a.value > b.value ? a : b).name.replace(/_/g, ' ')
        : 'None'

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

            {/* Stat Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                    title="Total Violations"
                    value={summary?.total_violations || 0}
                    subtitle="all time"
                    color="red"
                    icon={<AlertTriangle size={18} />}
                />
                <StatCard
                    title="Today"
                    value={summary?.today_violations || 0}
                    subtitle="violations today"
                    color="orange"
                    icon={<TrendingUp size={18} />}
                />
                <StatCard
                    title="Cameras"
                    value={`${summary?.cameras_active || 0} / ${summary?.cameras_total || 0}`}
                    subtitle="active / total"
                    color="green"
                    icon={<Camera size={18} />}
                />
                <StatCard
                    title="Most Common"
                    value={mostCommon}
                    subtitle="violation type"
                    color="purple"
                    icon={<Shield size={18} />}
                />
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Bar Chart — 7-day timeline */}
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                    <h3 className="text-sm font-semibold text-gray-700 mb-4">Violations — Last 7 Days</h3>
                    <ResponsiveContainer width="100%" height={240}>
                        <BarChart data={timeline}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                            <XAxis
                                dataKey="date"
                                tickFormatter={(d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                tick={{ fontSize: 11, fill: '#9ca3af' }}
                            />
                            <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} allowDecimals={false} />
                            <Tooltip
                                contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb' }}
                                labelFormatter={(d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
                            />
                            <Bar dataKey="count" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* Pie/Donut Chart */}
                <div className="bg-white rounded-2xl border border-gray-200 p-5">
                    <h3 className="text-sm font-semibold text-gray-700 mb-4">By Violation Type</h3>
                    {pieData.length > 0 ? (
                        <ResponsiveContainer width="100%" height={240}>
                            <PieChart>
                                <Pie
                                    data={pieData}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={90}
                                    paddingAngle={3}
                                    dataKey="value"
                                    label={({ name, value }) => `${name.replace(/_/g, ' ')} (${value})`}
                                    labelLine={false}
                                >
                                    {pieData.map((entry) => (
                                        <Cell
                                            key={entry.name}
                                            fill={PIE_COLORS[entry.name] || '#6b7280'}
                                        />
                                    ))}
                                </Pie>
                                <Tooltip />
                            </PieChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-60 flex items-center justify-center text-sm text-gray-400">
                            No violations to display
                        </div>
                    )}
                </div>
            </div>

            {/* Recent Violations */}
            <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Recent Violations</h3>
                <ViolationTable
                    violations={summary?.recent_violations || []}
                    onViewEvidence={setSelectedViolation}
                />
            </div>

            {selectedViolation && (
                <EvidenceModal
                    violation={selectedViolation}
                    onClose={() => setSelectedViolation(null)}
                />
            )}
        </div>
    )
}
