import { useState, useEffect } from "react";
import { Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import useCameraStore from "../store/cameraStore";
import CameraCard from "../components/CameraCard";
import socket, {
  connectSocket,
  subscribeCamera,
  unsubscribeCamera,
} from "../services/socket";

export default function Cameras() {
  const { t } = useTranslation();
  const {
    cameras,
    fetchCameras,
    addCamera,
    deleteCamera,
    updateFrame,
    updateCameraStatus,
    loading,
  } = useCameraStore();
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ camera_id: "", location: "", source: "" });
  const [formError, setFormError] = useState("");

  useEffect(() => {
    fetchCameras();
    connectSocket();

    // Listen for frame events
    const handleFrame = (data) => {
      updateFrame(data.camera_id, data.jpeg_b64);
    };

    // Listen for camera status changes from backend (e.g., error, stopped)
    const handleCameraStatus = (data) => {
      console.log("[Socket] Camera status:", data);
      updateCameraStatus(data.camera_id, data.status);
    };

    socket.on("frame", handleFrame);
    socket.on("camera_status", handleCameraStatus);

    return () => {
      socket.off("frame", handleFrame);
      socket.off("camera_status", handleCameraStatus);
    };
  }, []);

  // Subscribe to all running cameras when cameras list changes
  useEffect(() => {
    cameras.forEach((cam) => {
      if (cam.status === "running") {
        subscribeCamera(cam.camera_id);
      }
    });
    return () => {
      cameras.forEach((cam) => unsubscribeCamera(cam.camera_id));
    };
  }, [cameras]);

  const handleAdd = async (e) => {
    e.preventDefault();
    setFormError("");

    if (!form.camera_id || !form.location || !form.source) {
      setFormError(t("All fields are required"));
      return;
    }

    try {
      await addCamera(form);
      setShowModal(false);
      setForm({ camera_id: "", location: "", source: "" });
    } catch (err) {
      setFormError(err.response?.data?.detail || t("Failed to add camera"));
    }
  };

  const handleDelete = async (cameraId) => {
    if (!confirm(`${t("Delete camera")} ${cameraId}?`)) return;
    try {
      unsubscribeCamera(cameraId);
      await deleteCamera(cameraId);
    } catch (err) {
      alert(t("Failed to delete camera"));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("Cameras")}</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors"
        >
          <Plus size={16} /> {t("Add Camera")}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : cameras.length === 0 ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-16 text-center">
          <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
          </div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">
            {t("No cameras added")}
          </h3>
          <p className="text-xs text-gray-400 mb-4">
            {t("Add a camera to start live detection")}
          </p>
          <button
            onClick={() => setShowModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            + {t("Add Camera")}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {cameras.map((cam) => (
            <CameraCard
              key={cam.camera_id}
              camera={cam}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Add Camera Modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-white rounded-2xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-bold text-gray-900">
                {t("Add Camera")}
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 hover:bg-gray-100 rounded-lg"
              >
                <X size={18} className="text-gray-500" />
              </button>
            </div>

            {formError && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-2.5 mb-4">
                {formError}
              </div>
            )}

            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1.5 block">
                  {t("Camera ID")}
                </label>
                <input
                  type="text"
                  value={form.camera_id}
                  onChange={(e) =>
                    setForm({ ...form, camera_id: e.target.value })
                  }
                  className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. CAM-001"
                  required
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1.5 block">
                  {t("Location")}
                </label>
                <input
                  type="text"
                  value={form.location}
                  onChange={(e) =>
                    setForm({ ...form, location: e.target.value })
                  }
                  className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. NH-44 Toll Gate, Bangalore"
                  required
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1.5 block">
                  {t("Source")}
                </label>
                <input
                  type="text"
                  value={form.source}
                  onChange={(e) => setForm({ ...form, source: e.target.value })}
                  className="w-full px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="0 (webcam) or rtsp://..."
                  required
                />
                <p className="text-xs text-gray-400 mt-1">
                  {t("Enter a number for webcam index or a URL for IP camera")}
                </p>
              </div>
              <button
                type="submit"
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm py-2.5 rounded-lg transition-colors"
              >
                {t("Add Camera")}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
