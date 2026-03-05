import { useEffect, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

const BADGE_BG = {
    NO_HELMET: 'bg-red-500',
    TRIPLE_RIDING: 'bg-orange-500',
    CO_RIDING_NO_HELMET: 'bg-purple-500',
}

export default function ViolationToast({ violation, onDismiss }) {
    const [visible, setVisible] = useState(false)

    useEffect(() => {
        // Animate in
        const t1 = setTimeout(() => setVisible(true), 50)
        // Auto dismiss after 5 seconds
        const t2 = setTimeout(() => {
            setVisible(false)
            setTimeout(onDismiss, 300)
        }, 5000)
        return () => { clearTimeout(t1); clearTimeout(t2) }
    }, [onDismiss])

    const bg = BADGE_BG[violation?.violation_type] || 'bg-gray-600'

    return (
        <div
            className={`
        fixed top-20 right-6 z-50 max-w-sm w-full
        transition-all duration-300
        ${visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}
      `}
        >
            <div className={`${bg} text-white rounded-xl p-4 shadow-lg`}>
                <div className="flex items-start gap-3">
                    <AlertTriangle size={20} className="flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                        <p className="text-sm font-semibold">
                            {violation?.violation_type?.replace(/_/g, ' ')}
                        </p>
                        <p className="text-xs opacity-80 mt-0.5">
                            Camera: {violation?.camera_id}
                            {violation?.plate_text && ` · Plate: ${violation.plate_text}`}
                        </p>
                    </div>
                    <button
                        onClick={() => { setVisible(false); setTimeout(onDismiss, 300) }}
                        className="text-white/70 hover:text-white"
                    >
                        <X size={16} />
                    </button>
                </div>
            </div>
        </div>
    )
}
