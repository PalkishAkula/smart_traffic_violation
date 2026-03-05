import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

export default function Processing({ apiBase }) {
    const { jobId } = useParams()
    const navigate = useNavigate()
    const [job, setJob] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${apiBase}/status/${jobId}`)
                if (!res.ok) throw new Error('Failed to fetch status')
                const data = await res.json()
                setJob(data)

                if (data.status === 'done') {
                    clearInterval(interval)
                    setTimeout(() => navigate(`/results/${jobId}`), 1000)
                } else if (data.status === 'failed') {
                    clearInterval(interval)
                }
            } catch (err) {
                setError(err.message)
            }
        }, 2000)

        // Fetch immediately
        fetch(`${apiBase}/status/${jobId}`)
            .then(r => r.json())
            .then(data => setJob(data))
            .catch(err => setError(err.message))

        return () => clearInterval(interval)
    }, [apiBase, jobId, navigate])

    if (error) {
        return (
            <div className="max-w-2xl mx-auto text-center">
                <div className="bg-red-50 border border-red-200 rounded-xl p-6">
                    <h2 className="text-lg font-semibold text-red-700 mb-2">Error</h2>
                    <p className="text-sm text-red-600">{error}</p>
                </div>
            </div>
        )
    }

    if (!job) {
        return (
            <div className="max-w-2xl mx-auto text-center py-20">
                <div className="animate-spin w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full mx-auto mb-4" />
                <p className="text-gray-500">Loading...</p>
            </div>
        )
    }

    const statusColor = {
        pending: 'text-yellow-600',
        processing: 'text-blue-600',
        done: 'text-green-600',
        failed: 'text-red-600',
    }

    return (
        <div className="max-w-2xl mx-auto">
            <div className="text-center mb-8">
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Processing Video</h1>
                <p className="text-gray-500">{job.input_filename}</p>
            </div>

            {/* Status Card */}
            <div className="bg-white rounded-2xl border border-gray-200 p-8 mb-6">
                {/* Status Badge */}
                <div className="flex items-center justify-center mb-6">
                    <span className={`text-sm font-semibold uppercase tracking-wider ${statusColor[job.status] || 'text-gray-600'}`}>
                        {job.status === 'processing' && (
                            <span className="inline-block w-2 h-2 bg-blue-500 rounded-full mr-2 animate-pulse" />
                        )}
                        {job.status}
                    </span>
                </div>

                {/* Progress Bar */}
                {(job.status === 'processing' || job.status === 'pending') && (
                    <div className="mb-6">
                        <div className="flex justify-between mb-2 text-sm">
                            <span className="text-gray-600">Progress</span>
                            <span className="font-semibold text-gray-900">{job.progress_pct.toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-3">
                            <div
                                className="bg-blue-600 h-3 rounded-full transition-all duration-500 ease-out"
                                style={{ width: `${job.progress_pct}%` }}
                            />
                        </div>
                    </div>
                )}

                {/* Stats Grid */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                    <div className="bg-gray-50 rounded-xl p-4 text-center">
                        <p className="text-2xl font-bold text-gray-900">
                            {job.current_frame}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">Current Frame</p>
                    </div>
                    <div className="bg-gray-50 rounded-xl p-4 text-center">
                        <p className="text-2xl font-bold text-gray-900">
                            {job.total_frames}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">Total Frames</p>
                    </div>
                    <div className="bg-gray-50 rounded-xl p-4 text-center">
                        <p className="text-2xl font-bold text-blue-600">
                            {job.current_fps.toFixed(1)}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">FPS</p>
                    </div>
                </div>

                {/* Done Message */}
                {job.status === 'done' && (
                    <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
                        <p className="text-green-700 font-medium">
                            ✓ Processing complete! Redirecting to results...
                        </p>
                    </div>
                )}

                {/* Failed Message */}
                {job.status === 'failed' && (
                    <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                        <p className="text-red-700 font-medium mb-1">Processing Failed</p>
                        <p className="text-sm text-red-600">{job.error_message}</p>
                    </div>
                )}
            </div>

            {/* Live Log */}
            {job.log_lines && job.log_lines.length > 0 && (
                <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-100">
                        <h3 className="text-sm font-semibold text-gray-700">Live Log</h3>
                    </div>
                    <div className="bg-gray-900 p-4 max-h-64 overflow-y-auto font-mono text-xs">
                        {job.log_lines.map((line, i) => (
                            <div key={i} className="text-green-400 py-0.5 leading-relaxed">
                                {line}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
