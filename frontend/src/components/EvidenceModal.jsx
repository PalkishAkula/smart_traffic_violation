import { X } from 'lucide-react'

export default function EvidenceModal({ violation, onClose }) {
    if (!violation) return null

    const BADGE_STYLES = {
        NO_HELMET: 'bg-red-100 text-red-700',
        TRIPLE_RIDING: 'bg-orange-100 text-orange-700',
        CO_RIDING_NO_HELMET: 'bg-purple-100 text-purple-700',
    }

    return (
        <div
            className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-auto"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-gray-100">
                    <div>
                        <h3 className="text-sm font-bold text-gray-900">Violation Evidence</h3>
                        <p className="text-xs text-gray-500 mt-0.5">
                            Camera: {violation.camera_id} · Track #{violation.track_id}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <X size={18} className="text-gray-500" />
                    </button>
                </div>

                {/* Image */}
                <div className="bg-gray-900 flex items-center justify-center">
                    {violation.evidence_url ? (
                        <img
                            src={violation.evidence_url}
                            alt="Violation evidence"
                            className="max-w-full max-h-[60vh] object-contain"
                        />
                    ) : (
                        <div className="py-20 text-center text-gray-500 text-sm">
                            No evidence image available
                        </div>
                    )}
                </div>

                {/* Details */}
                <div className="p-5 grid grid-cols-2 gap-4">
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Violation Type</p>
                        <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${BADGE_STYLES[violation.violation_type] || 'bg-gray-100 text-gray-700'}`}>
                            {violation.violation_type?.replace(/_/g, ' ')}
                        </span>
                    </div>
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Plate Number</p>
                        <p className="text-sm font-mono font-medium">
                            {violation.plate_text || <span className="text-gray-400 italic">UNDETECTED</span>}
                        </p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Confidence</p>
                        <p className="text-sm">{violation.plate_conf ? `${(violation.plate_conf * 100).toFixed(1)}%` : '—'}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Detected At</p>
                        <p className="text-sm text-gray-700">
                            {violation.detected_at ? new Date(violation.detected_at).toLocaleString() : '—'}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
