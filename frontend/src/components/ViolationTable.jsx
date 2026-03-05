import { useState } from 'react'



const BADGE_STYLES = {

    NO_HELMET: 'bg-red-100 text-red-700',

    TRIPLE_RIDING: 'bg-orange-100 text-orange-700',

    CO_RIDING_NO_HELMET: 'bg-purple-100 text-purple-700',

}



const TYPE_LABELS = {

    NO_HELMET: 'No Helmet',

    TRIPLE_RIDING: 'Triple Riding',

    CO_RIDING_NO_HELMET: 'Co-rider No Helmet',

}



export default function ViolationTable({ violations, onViewEvidence, onDelete, showCamera = true }) {

    const formatDate = (iso) => {

        if (!iso) return '—'

        const d = new Date(iso)

        return d.toLocaleDateString('en-US', {

            month: 'short', day: 'numeric', year: 'numeric'

        }) + ' · ' + d.toLocaleTimeString('en-US', {

            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false

        })

    }

    const getViolationId = (v) => v?.id || v?._id



    return (

        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">

            {violations.length === 0 ? (

                <div className="p-12 text-center text-sm text-gray-400">

                    No violations found

                </div>

            ) : (

                <div className="overflow-x-auto">

                    <table className="w-full">

                        <thead>

                            <tr className="border-b border-gray-100">

                                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">#</th>

                                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Evidence</th>

                                {showCamera && <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Camera</th>}

                                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Type</th>

                                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Plate</th>

                                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Detected</th>

                                <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Confidence</th>

                                {onDelete && <th className="px-5 py-3"></th>}

                            </tr>

                        </thead>

                        <tbody>

                            {violations.map((v, i) => (

                                <tr key={getViolationId(v) || i} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">

                                    <td className="px-5 py-3 text-sm text-gray-400">{i + 1}</td>

                                    <td className="px-5 py-3">

                                        {v.evidence_url ? (

                                            <img

                                                src={v.evidence_url}

                                                alt="evidence"

                                                className="w-14 h-10 object-cover rounded-lg cursor-pointer hover:opacity-80 transition-opacity border border-gray-200"

                                                onClick={() => onViewEvidence?.(v)}

                                            />

                                        ) : (

                                            <div className="w-14 h-10 bg-gray-100 rounded-lg flex items-center justify-center">

                                                <span className="text-[10px] text-gray-400">N/A</span>

                                            </div>

                                        )}

                                    </td>

                                    {showCamera && (

                                        <td className="px-5 py-3 text-sm font-medium text-gray-900">

                                            {v.camera_id}

                                        </td>

                                    )}

                                    <td className="px-5 py-3">

                                        <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${BADGE_STYLES[v.violation_type] || 'bg-gray-100 text-gray-700'}`}>

                                            {TYPE_LABELS[v.violation_type] || v.violation_type?.replace(/_/g, ' ')}

                                        </span>

                                    </td>

                                    <td className="px-5 py-3 text-sm">

                                        {v.plate_text ? (

                                            <span className="font-mono font-medium text-gray-900">{v.plate_text}</span>

                                        ) : (

                                            <span className="text-gray-400 italic text-xs">UNDETECTED</span>

                                        )}

                                    </td>

                                    <td className="px-5 py-3 text-xs text-gray-500">

                                        {formatDate(v.detected_at)}

                                    </td>

                                    <td className="px-5 py-3 text-sm text-gray-500">

                                        {v.plate_conf != null && v.plate_text ? (

                                            <span>{(v.plate_conf * 100).toFixed(1)}%</span>

                                        ) : (

                                            <span className="text-gray-300">—</span>

                                        )}

                                    </td>

                                    {onDelete && (

                                        <td className="px-5 py-3">

                                            <button

                                                onClick={() => {
                                                    const id = getViolationId(v)
                                                    if (!id) return
                                                    onDelete(v)
                                                }}

                                                disabled={!getViolationId(v)}

                                                className="text-gray-400 hover:text-red-500 text-xs disabled:opacity-30 disabled:hover:text-gray-400"

                                            >

                                                Delete

                                            </button>

                                        </td>

                                    )}

                                </tr>

                            ))}

                        </tbody>

                    </table>

                </div>

            )}

        </div>

    )

}

