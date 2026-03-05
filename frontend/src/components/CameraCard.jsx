import { useState } from 'react'
import { Play, Square, Trash2, MapPin, Camera, Maximize2, X, Minimize2 } from 'lucide-react'
import useCameraStore from '../store/cameraStore'

export default function CameraCard({ camera, onDelete }) {
    const { startCamera, stopCamera, frames } = useCameraStore()
    const frameUrl = frames[camera.camera_id]
    const isRunning = camera.status === 'running'
    const [expanded, setExpanded] = useState(false)

    const handleStart = async () => {
        try { await startCamera(camera.camera_id) }
        catch (err) { alert('Failed to start camera') }
    }

    const handleStop = async () => {
        try { await stopCamera(camera.camera_id) }
        catch (err) { alert('Failed to stop camera') }
    }

    return (
        <>
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
                {/* Live Preview */}
                <div className="aspect-video bg-gray-900 relative flex items-center justify-center group">
                    {isRunning && frameUrl ? (
                        <img
                            src={frameUrl}
                            alt="Live feed"
                            className="w-full h-full object-cover"
                        />
                    ) : (
                        <div className="text-center">
                            <Camera size={32} className="text-gray-600 mx-auto mb-2" />
                            <p className="text-xs text-gray-500">No live feed</p>
                        </div>
                    )}

                    {/* Expand button — visible on hover */}
                    {isRunning && frameUrl && (
                        <button
                            onClick={() => setExpanded(true)}
                            className="absolute top-3 left-3 p-2 bg-black/50 hover:bg-black/80 text-white rounded-lg opacity-0 group-hover:opacity-100 transition-all backdrop-blur-sm cursor-pointer"
                            title="View fullscreen"
                        >
                            <Maximize2 size={16} />
                        </button>
                    )}

                    {/* Status badge */}
                    <div className="absolute top-3 right-3">
                        <span className={`
                            inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold
                            ${isRunning
                                ? 'bg-green-500/90 text-white'
                                : camera.status === 'error'
                                    ? 'bg-red-500/90 text-white'
                                    : 'bg-gray-600/80 text-white'
                            }
                        `}>
                            <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-white animate-pulse' : 'bg-gray-300'}`} />
                            {camera.status?.toUpperCase()}
                        </span>
                    </div>
                </div>

                {/* Info */}
                <div className="p-4">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-sm font-bold text-gray-900">{camera.camera_id}</h3>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-4">
                        <MapPin size={12} />
                        <span>{camera.location}</span>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                        {!isRunning ? (
                            <button
                                onClick={handleStart}
                                className="flex-1 flex items-center justify-center gap-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-semibold py-2 rounded-lg transition-colors"
                            >
                                <Play size={14} /> Start
                            </button>
                        ) : (
                            <>
                                <button
                                    onClick={handleStop}
                                    className="flex-1 flex items-center justify-center gap-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold py-2 rounded-lg transition-colors"
                                >
                                    <Square size={14} /> Stop
                                </button>
                                <button
                                    onClick={() => setExpanded(true)}
                                    className="flex items-center justify-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold py-2 px-3 rounded-lg transition-colors"
                                    title="Expand view"
                                >
                                    <Maximize2 size={14} />
                                </button>
                            </>
                        )}
                        <button
                            onClick={() => onDelete(camera.camera_id)}
                            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        >
                            <Trash2 size={14} />
                        </button>
                    </div>
                </div>
            </div>

            {/* ── Fullscreen Live View Modal ──────────────────────────────── */}
            {expanded && (
                <div
                    className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4"
                    onClick={() => setExpanded(false)}
                >
                    <div
                        className="relative w-full max-w-5xl"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Header bar */}
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-3">
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-green-500/90 text-white rounded-full text-xs font-semibold">
                                    <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
                                    LIVE
                                </span>
                                <h2 className="text-white font-bold text-lg">{camera.camera_id}</h2>
                                <span className="text-gray-400 text-sm flex items-center gap-1">
                                    <MapPin size={12} /> {camera.location}
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handleStop}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors"
                                >
                                    <Square size={12} /> Stop Camera
                                </button>
                                <button
                                    onClick={() => setExpanded(false)}
                                    className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                                    title="Close"
                                >
                                    <X size={20} />
                                </button>
                            </div>
                        </div>

                        {/* Live video feed — large */}
                        <div className="rounded-xl overflow-hidden bg-gray-900 border border-gray-700/50">
                            {frameUrl ? (
                                <img
                                    src={frameUrl}
                                    alt={`Live feed — ${camera.camera_id}`}
                                    className="w-full h-auto max-h-[80vh] object-contain"
                                />
                            ) : (
                                <div className="aspect-video flex items-center justify-center">
                                    <div className="text-center">
                                        <Camera size={48} className="text-gray-600 mx-auto mb-3" />
                                        <p className="text-sm text-gray-500">Camera stopped — no live feed</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Footer info */}
                        <div className="mt-3 flex items-center justify-between">
                            <p className="text-xs text-gray-500">
                                Source: {camera.source || 'Unknown'}
                            </p>
                            <p className="text-xs text-gray-500">
                                Press <kbd className="px-1.5 py-0.5 bg-gray-800 text-gray-300 rounded text-[10px] font-mono">ESC</kbd> or click outside to close
                            </p>
                        </div>
                    </div>
                </div>
            )}
        </>
    )
}
