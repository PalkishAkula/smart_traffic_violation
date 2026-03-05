export default function VideoPlayer({ apiBase, jobId }) {
    const videoUrl = `${apiBase}/video/${jobId}`

    const handleDownload = () => {
        const a = document.createElement('a')
        a.href = videoUrl
        a.download = `annotated_video_${jobId}.mp4`
        a.click()
    }

    return (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-700">Annotated Video</h3>
                <button
                    onClick={handleDownload}
                    className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 font-medium transition-colors"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download
                </button>
            </div>
            <div className="bg-black">
                <video
                    controls
                    className="w-full max-h-[500px]"
                    src={videoUrl}
                >
                    Your browser does not support the video tag.
                </video>
            </div>
        </div>
    )
}
