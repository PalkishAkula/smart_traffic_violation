import { useEffect, useRef, useState } from "react";
import { Upload as UploadIcon, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import api from "../services/api";

function prettyType(type) {
  return (type || "").replaceAll("_", " ");
}

export default function ImageTest() {
  const { t } = useTranslation();
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileInput = useRef(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  const resetAll = () => {
    setFile(null);
    setResult(null);
    setError("");
    setLoading(false);
  };

  const runImageTest = async () => {
    if (!file || loading) return;

    setLoading(true);
    setError("");
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await api.post("/api/upload/image", formData);
      setResult(res.data);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          "Image analysis failed. Please try another image.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      setFile(droppedFile);
      setResult(null);
      setError("");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{t("Image Test")}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {t("Upload a single image to view violation detection, OCR text, and bounding boxes.")}
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-4">
        <div
          className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
            dragActive
              ? "border-blue-500 bg-blue-50"
              : "border-gray-300 bg-gray-50 hover:border-gray-400"
          }`}
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
            accept=".jpg,.jpeg,.png,.bmp,.webp"
            className="hidden"
            onChange={(e) => {
              const picked = e.target.files?.[0];
              if (picked) {
                setFile(picked);
                setResult(null);
                setError("");
              }
            }}
          />
          <div className="w-12 h-12 bg-white rounded-xl border border-gray-200 flex items-center justify-center mx-auto mb-3">
            <UploadIcon className="text-gray-500" size={22} />
          </div>
          {file ? (
            <div>
              <p className="text-sm font-semibold text-gray-800">{file.name}</p>
              <p className="text-xs text-gray-500 mt-1">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          ) : (
            <div>
              <p className="text-sm font-semibold text-gray-700">
                {t("Drag & drop an image here")}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {t("or click to browse (JPG, PNG, BMP, WEBP)")}
              </p>
            </div>
          )}
        </div>

        {previewUrl && (
          <div className="border border-gray-200 rounded-xl overflow-hidden bg-black/5">
            <img
              src={previewUrl}
              alt="Input preview"
              className="max-h-[360px] w-full object-contain"
            />
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={runImageTest}
            disabled={!file || loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors inline-flex items-center gap-2"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : null}
            {loading ? t("Analyzing Image...") : t("Analyze Image")}
          </button>
          <button
            onClick={resetAll}
            className="text-sm text-gray-600 hover:text-gray-800 px-2 py-2"
          >
            {t("Reset")}
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700 flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {result && (
        <div className="space-y-4">
          <div className="bg-green-50 border border-green-200 rounded-2xl px-4 py-3 text-green-800 text-sm font-medium flex items-center gap-2">
            <CheckCircle2 size={18} />
            {t("Image analysis complete")}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-white border border-gray-200 rounded-xl p-3">
              <p className="text-xs text-gray-500">{t("Bikes")}</p>
              <p className="text-xl font-bold text-gray-900">{result.summary?.total_bikes ?? 0}</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-3">
              <p className="text-xs text-gray-500">{t("Violations")}</p>
              <p className="text-xl font-bold text-gray-900">{result.summary?.total_violations ?? 0}</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-3">
              <p className="text-xs text-gray-500">{t("OCR Reads")}</p>
              <p className="text-xl font-bold text-gray-900">{result.summary?.total_ocr_reads ?? 0}</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-3">
              <p className="text-xs text-gray-500">{t("Plate Boxes")}</p>
              <p className="text-xl font-bold text-gray-900">{result.summary?.total_plate_boxes ?? 0}</p>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              {t("Annotated Output")}
            </h2>
            <div className="rounded-xl overflow-hidden border border-gray-100 bg-black/5">
              <img
                src={`data:image/jpeg;base64,${result.annotated_image_b64}`}
                alt="Annotated detection output"
                className="w-full max-h-[700px] object-contain"
              />
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-4 overflow-x-auto">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              {t("Bike OCR and Violations")}
            </h2>
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="py-2 pr-3">{t("Track")}</th>
                  <th className="py-2 pr-3">{t("Plate")}</th>
                  <th className="py-2 pr-3">{t("Confidence")}</th>
                  <th className="py-2 pr-3">{t("Type")}</th>
                  <th className="py-2 pr-3">Bike Box</th>
                  <th className="py-2 pr-3">Plate Box</th>
                </tr>
              </thead>
              <tbody>
                {(result.bikes || []).map((bike) => (
                  <tr key={bike.track_id} className="border-b border-gray-100">
                    <td className="py-2 pr-3 font-medium text-gray-900">#{bike.track_id}</td>
                    <td className="py-2 pr-3 font-mono">
                      {bike.plate_text || t("UNDETECTED")}
                    </td>
                    <td className="py-2 pr-3">
                      {bike.plate_conf ? `${(bike.plate_conf * 100).toFixed(1)}%` : "-"}
                    </td>
                    <td className="py-2 pr-3">
                      {bike.violation_types?.length
                        ? bike.violation_types.map(prettyType).join(", ")
                        : "NONE"}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-600 font-mono">
                      {bike.bike_box?.slice(0, 4).join(", ")}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-600 font-mono">
                      {bike.plate_box ? bike.plate_box.join(", ") : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">
              {t("Violation Records")}
            </h2>
            {(result.violations || []).length === 0 ? (
              <p className="text-sm text-gray-500">{t("No violations found")}</p>
            ) : (
              <div className="space-y-2">
                {result.violations.map((v, i) => (
                  <div
                    key={`${v.track_id}-${v.violation_type}-${i}`}
                    className="border border-gray-100 rounded-lg px-3 py-2 text-sm"
                  >
                    <p className="font-medium text-gray-800">
                      #{v.track_id} • {prettyType(v.violation_type)}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      Plate: {v.plate_text || t("UNDETECTED")} | Bike Box: {v.bike_box?.join(", ")}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
