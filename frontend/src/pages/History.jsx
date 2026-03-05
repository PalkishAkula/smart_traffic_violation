import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

export default function History({ apiBase }) {
    const [jobs, setJobs] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    const fetchJobs = async () => {
        try {
            const res = await fetch(`${apiBase}/jobs`)
            if (!res.ok) throw new Error('Failed to fetch jobs')
            const data = await res.json()
            setJobs(data)
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchJobs()
    }, [apiBase])

    const handleDelete = async (jobId) => {
        if (!window.confirm('Are you sure you want to delete this job?')) return
        try {
            await fetch(`${apiBase}/jobs/${jobId}`, { method: 'DELETE' })
            setJobs(jobs.filter(j => j.job_id !== jobId))
        } catch (err) {
            alert('Failed to delete job')
        }
    }

    const statusBadge = (status) => {
        const styles = {
            pending: 'bg-yellow-100 text-yellow-700',
            processing: 'bg-blue-100 text-blue-700',
            done: 'bg-green-100 text-green-700',
            failed: 'bg-red-100 text-red-700',
        }
        return (
            <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${styles[status] || 'bg-gray-100 text-gray-700'}`}>
                {status?.toUpperCase()}
            </span>
        )
    }

    const formatDate = (iso) => {
        if (!iso) return '—'
        return new Date(iso).toLocaleString()
    }

    if (loading) {
        return (
            <div className="text-center py-20">
                <div className="animate-spin w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full mx-auto mb-4" />
                <p className="text-gray-500">Loading history...</p>
            </div>
        )
    }

    return (
        <div>
            <div className="flex items-center justify-between mb-8">
                <h1 className="text-3xl font-bold text-gray-900">Processing History</h1>
                <Link
                    to="/"
                    className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-5 rounded-xl transition-colors no-underline"
                >
                    + New Upload
                </Link>
            </div>

            {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
                    <p className="text-sm text-red-700">{error}</p>
                </div>
            )}

            {jobs.length === 0 ? (
                <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center">
                    <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                        <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-1">No jobs yet</h3>
                    <p className="text-sm text-gray-400">Upload a video to get started</p>
                </div>
            ) : (
                <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-100">
                                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Filename</th>
                                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Violations</th>
                                <th className="text-right px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {jobs.map((job) => (
                                <tr key={job.job_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                                    <td className="px-6 py-4">
                                        <p className="text-sm font-medium text-gray-900">{job.input_filename}</p>
                                        <p className="text-xs text-gray-400 mt-0.5 font-mono">{job.job_id.slice(0, 8)}...</p>
                                    </td>
                                    <td className="px-6 py-4">
                                        {statusBadge(job.status)}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600">
                                        {formatDate(job.created_at)}
                                    </td>
                                    <td className="px-6 py-4 text-sm font-semibold text-gray-900">
                                        {job.violation_summary?.total || 0}
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <div className="flex items-center justify-end gap-2">
                                            {job.status === 'done' && (
                                                <Link
                                                    to={`/results/${job.job_id}`}
                                                    className="text-blue-600 hover:text-blue-800 text-sm font-medium no-underline"
                                                >
                                                    View
                                                </Link>
                                            )}
                                            {job.status === 'processing' && (
                                                <Link
                                                    to={`/processing/${job.job_id}`}
                                                    className="text-blue-600 hover:text-blue-800 text-sm font-medium no-underline"
                                                >
                                                    Monitor
                                                </Link>
                                            )}
                                            <button
                                                onClick={() => handleDelete(job.job_id)}
                                                className="text-red-500 hover:text-red-700 text-sm font-medium ml-2"
                                            >
                                                Delete
                                            </button>
                                        </div>
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
