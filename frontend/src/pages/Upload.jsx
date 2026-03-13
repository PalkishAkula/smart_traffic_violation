import { useState, useRef, useEffect } from "react";
import { Upload as UploadIcon, CheckCircle, AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import api, { API_BASE } from "../services/api";
import ViolationTable from "../components/ViolationTable";
import EvidenceModal from "../components/EvidenceModal";

export default function Upload() {
  const { t } = useTranslation();
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [progressPct, setProgressPct] = useState(0);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [totalFrames, setTotalFrames] = useState(0);
  const [currentFps, setCurrentFps] = useState(0);
  const [logLines, setLogLines] = useState([]);
  const [violations, setViolations] = useState([]);
  const [error, setError] = useState(null);
  const [selectedViolation, setSelectedViolation] = useState(null);
  const fileInput = useRef(null);
  const logRef = useRef(null);

  // Auto-scroll log panel to bottom
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines]);

  // ── Robust polling ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/upload/status/${jobId}`);
        const data = res.data;

        // Update progress fields
        if (data.progress_pct !== undefined) setProgressPct(data.progress_pct);
        if (data.current_frame !== undefined)
          setCurrentFrame(data.current_frame);
        if (data.total_frames !== undefined) setTotalFrames(data.total_frames);
        if (data.current_fps !== undefined) setCurrentFps(data.current_fps);
        if (data.log_lines) setLogLines(data.log_lines);

        if (data.status === "done") {
          clearInterval(interval);
          setJobStatus("done");
          setProgressPct(100);
          setViolations(data.violations ?? []);
          return;
        }

        if (data.status === "error") {
          clearInterval(interval);
          setJobStatus("error");
          setError(data.error || "Processing failed. Check server logs.");
          return;
        }

        if (data.status === "not_found") {
          clearInterval(interval);
          setJobStatus("error");
          setError("Job not found on server.");
          return;
        }

        // status === 'processing' → keep polling
        setJobStatus("processing");
      } catch (networkErr) {
        clearInterval(interval);
        setJobStatus("error");
        setError("Could not reach server. Is the backend running?");
      }
    }, 2000);

    // Hard safety timeout: 15 minutes
    const timeout = setTimeout(
      () => {
        clearInterval(interval);
        setJobStatus((prev) => {
          if (prev === "processing") {
            setError("Processing timed out after 15 minutes.");
            return "error";
          }
          return prev;
        });
      },
      15 * 60 * 1000,
    );

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [jobId]);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) setFile(droppedFile);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadProgress(0);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await api.post("/api/upload/video", formData, {
        onUploadProgress: (e) => {
          setUploadProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      setJobId(res.data.job_id);
      setJobStatus("processing");
      setProgressPct(0);
      setLogLines([]);
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setJobId(null);
    setJobStatus(null);
    setViolations([]);
    setUploadProgress(0);
    setProgressPct(0);
    setCurrentFrame(0);
    setTotalFrames(0);
    setCurrentFps(0);
    setLogLines([]);
    setError(null);
  };

  // ── RESULTS VIEW ──────────────────────────────────────────────────────────
  if (jobStatus === "done") {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">{t("Results")}</h1>
          <button
            onClick={reset}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            ← {t("Upload Another")}
          </button>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-2xl p-5 flex items-center gap-3">
          <CheckCircle className="text-green-600" size={24} />
          <p className="text-sm font-semibold text-green-800">
            ✓ Done — {violations.length} violation
            {violations.length !== 1 ? "s" : ""} detected
          </p>
        </div>

        <ViolationTable
          violations={violations}
          showCamera={false}
          onViewEvidence={setSelectedViolation}
        />

        {/* Model Logs (collapsed by default) */}
        {logLines.length > 0 && (
          <details className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
            <summary className="px-5 py-3 text-sm font-semibold text-gray-700 cursor-pointer hover:bg-gray-50">
              {t("Model Logs")} ({logLines.length} {t("lines")})
            </summary>
            <div className="bg-gray-900 p-4 max-h-64 overflow-y-auto font-mono text-xs text-green-400 leading-relaxed">
              {logLines.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          </details>
        )}

        {selectedViolation && (
          <EvidenceModal
            violation={selectedViolation}
            onClose={() => setSelectedViolation(null)}
          />
        )}
      </div>
    );
  }

  // ── ERROR VIEW ────────────────────────────────────────────────────────────
  if (jobStatus === "error") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">
          {t("Upload Video")}
        </h1>
        <div className="bg-red-50 border border-red-200 rounded-2xl p-5 flex items-center gap-3">
          <AlertCircle className="text-red-600" size={24} />
          <div>
            <p className="text-sm font-semibold text-red-800">
              {t("Processing failed")}
            </p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
        </div>
        <button
          onClick={reset}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          ← {t("Try Again")}
        </button>
      </div>
    );
  }

  // ── PROCESSING VIEW ───────────────────────────────────────────────────────
  if (jobStatus === "processing") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">{t("Processing")}</h1>
        <div className="bg-white rounded-2xl border border-gray-200 p-6 max-w-xl mx-auto space-y-5">
          {/* Animated spinner + text */}
          <div className="flex flex-col items-center text-center gap-3 py-4">
            <div className="w-12 h-12 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
            <div>
              <p className="text-base font-semibold text-gray-800">
                {t("Analyzing video…")}
              </p>
              {totalFrames > 0 && (
                <p className="text-sm text-gray-500 mt-1">
                  Frame {currentFrame}/{totalFrames} · {currentFps.toFixed(1)}{" "}
                  FPS
                </p>
              )}
            </div>
          </div>

          {/* Progress bar */}
          <div>
            <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
              <div
                className="bg-blue-600 h-3 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${Math.min(progressPct, 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 text-right mt-1.5 font-medium">
              {progressPct.toFixed(1)}%
            </p>
          </div>

          {/* Live model logs */}
          {logLines.length > 0 && (
            <div
              ref={logRef}
              className="bg-gray-900 rounded-xl p-4 max-h-48 overflow-y-auto font-mono text-xs text-green-400 leading-relaxed"
            >
              {logLines.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── UPLOAD VIEW ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">{t("Upload Video")}</h1>
      <p className="text-sm text-gray-500">
        {t("Upload a traffic camera video to detect motorcycle violations")}
      </p>

      <div className="max-w-xl mx-auto">
        {/* Drop zone */}
        <div
          className={`
            border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all
            ${dragActive ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-white hover:border-gray-400"}
          `}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          onClick={() => fileInput.current?.click()}
        >
          <input
            ref={fileInput}
            type="file"
            accept=".mp4,.avi,.mov,.mkv"
            className="hidden"
            onChange={(e) => {
              if (e.target.files[0]) setFile(e.target.files[0]);
            }}
          />

          <div className="w-14 h-14 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <UploadIcon size={24} className="text-gray-400" />
          </div>

          {file ? (
            <div>
              <p className="text-sm font-semibold text-gray-700">{file.name}</p>
              <p className="text-xs text-gray-400 mt-1">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </p>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                }}
                className="text-xs text-red-500 hover:text-red-700 mt-2"
              >
                {t("Remove")}
              </button>
            </div>
          ) : (
            <div>
              <p className="text-sm font-semibold text-gray-700">
                {t("Drag & drop your video here")}
              </p>
              <p className="text-xs text-gray-400 mt-1">
                {t("or click to browse")}
              </p>
              <p className="text-xs text-gray-300 mt-2">
                {t("Supports MP4, AVI, MOV, MKV (max 500 MB)")}
              </p>
            </div>
          )}
        </div>

        {/* Upload progress */}
        {uploading && (
          <div className="mt-4">
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 text-right mt-1">
              {t("Uploading…")} {uploadProgress}%
            </p>
          </div>
        )}

        {/* Error during upload */}
        {error && !jobId && (
          <div className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2.5">
            {error}
          </div>
        )}

        {/* Submit */}
        {file && !uploading && !jobId && (
          <button
            onClick={handleUpload}
            className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm py-3 rounded-lg transition-colors"
          >
            {t("Start Processing")}
          </button>
        )}
      </div>
    </div>
  );
}
