import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import SummaryCards from '../components/SummaryCards'
import ViolationsTable from '../components/ViolationsTable'
import VideoPlayer from '../components/VideoPlayer'

export default function Results({ apiBase }) {
    const { jobId } = useParams()
    const [job, setJob] = useState(null)
    const [violations, setViolations] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        const fetchResults = async () => {
            try {
                const res = await fetch(`${apiBase}/results/${jobId}`)
                if (!res.ok) throw new Error('Failed to fetch results')
                const data = await res.json()
                setJob(data.job)
                setViolations(data.violations)
            } catch (err) {
                setError(err.message)
            } finally {
                setLoading(false)
            }
        }
        fetchResults()
    }, [apiBase, jobId])

    const exportCSV = () => {
        if (!violations.length) return

        const headers = ['Track ID', 'Violation Type', 'Plate Number', 'Confidence', 'Frame Number', 'Retries']
        const rows = violations.map(v => [
            v.track_id,
            v.violation_type,
            v.plate_text || 'UNDETECTED',
            v.plate_conf.toFixed(4),
            v.frame_number,
            v.plate_retries,
        ])

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `violations_${jobId}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    if (loading) {
        return (
            <div className="text-center py-20">
                <div className="animate-spin w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full mx-auto mb-4" />
                <p className="text-gray-500">Loading results...</p>
            </div>
        )
    }

    if (error) {
        return (
            <div className="max-w-2xl mx-auto">
                <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
                    <p className="text-red-700">{error}</p>
                </div>
            </div>
        )
    }

    const uniquePlates = new Set(
        violations.filter(v => v.plate_text).map(v => v.plate_text)
    ).size

    return (
        <div>
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">Results</h1>
                    <p className="text-gray-500 mt-1">{job?.input_filename}</p>
                </div>
                <button
                    onClick={exportCSV}
                    className="flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium py-2.5 px-5 rounded-xl transition-colors"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Export CSV
                </button>
            </div>

            {/* Summary Cards */}
            <SummaryCards
                summary={job?.violation_summary || {}}
                uniquePlates={uniquePlates}
            />

            {/* Video Player */}
            <div className="mt-8">
                <VideoPlayer apiBase={apiBase} jobId={jobId} />
            </div>

            {/* Violations Table */}
            <div className="mt-8">
                <ViolationsTable violations={violations} />
            </div>
        </div>
    )
}
