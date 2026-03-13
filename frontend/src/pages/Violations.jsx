import { useState, useEffect, useCallback } from "react";

import { Search, Filter, X, Download } from "lucide-react";

import { useTranslation } from "react-i18next";

import useViolationStore from "../store/violationStore";

import useCameraStore from "../store/cameraStore";

import ViolationTable from "../components/ViolationTable";

import EvidenceModal from "../components/EvidenceModal";

export default function Violations() {
  const { t } = useTranslation();

  const {
    violations,
    total,
    page,
    pages,
    loading,

    filters,
    setFilter,
    clearFilters,
    setPage,

    fetchViolations,
    deleteViolation,
  } = useViolationStore();

  const { cameras, fetchCameras } = useCameraStore();

  const [selectedViolation, setSelectedViolation] = useState(null);

  const [deleteTarget, setDeleteTarget] = useState(null);

  const [deleteLoading, setDeleteLoading] = useState(false);

  const [deleteError, setDeleteError] = useState(null);

  const [searchTimeout, setSearchTimeout] = useState(null);

  useEffect(() => {
    fetchViolations();

    fetchCameras();
  }, [page]);

  // Refetch when filters change (except plate_text which is debounced)

  useEffect(() => {
    fetchViolations();
  }, [
    filters.camera_id,
    filters.violation_type,
    filters.date_from,
    filters.date_to,
  ]);

  const handlePlateSearch = (value) => {
    setFilter("plate_text", value);

    if (searchTimeout) clearTimeout(searchTimeout);

    setSearchTimeout(
      setTimeout(() => {
        useViolationStore.getState().fetchViolations();
      }, 400),
    );
  };

  const getViolationId = (v) => v?.id || v?._id;

  const handleDelete = async (violation) => {
    setDeleteError(null);
    setDeleteTarget(violation);
  };

  const confirmDelete = async () => {
    const id = getViolationId(deleteTarget);
    if (!id) {
      setDeleteError("Cannot delete: missing violation id");
      return;
    }

    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await deleteViolation(id);
      setDeleteTarget(null);
    } catch (err) {
      const msg =
        err?.response?.data?.detail || err?.message || "Delete failed";
      setDeleteError(msg);
    } finally {
      setDeleteLoading(false);
    }
  };

  // CSV export

  const exportCSV = () => {
    const headers = [
      "Camera ID",
      "Violation Type",
      "Plate",
      "Confidence",
      "Detected At",
    ];

    const rows = violations.map((v) => [
      v.camera_id,

      v.violation_type,

      v.plate_text || "UNDETECTED",

      v.plate_conf ? `${(v.plate_conf * 100).toFixed(1)}%` : "",

      v.detected_at,
    ]);

    const csv = [headers, ...rows].map((r) => r.join(",")).join("\n");

    const blob = new Blob([csv], { type: "text/csv" });

    const a = document.createElement("a");

    a.href = URL.createObjectURL(blob);

    a.download = "violations_export.csv";

    a.click();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t("Violations")}</h1>

        <button
          onClick={exportCSV}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-800 font-medium border border-gray-300 rounded-lg px-3 py-2 hover:bg-gray-50 transition-colors"
        >
          <Download size={14} /> {t("Export CSV")}
        </button>
      </div>

      {/* Filter Bar */}

      <div className="bg-white rounded-2xl border border-gray-200 p-4">
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {/* Plate search */}

          <div className="relative col-span-2 lg:col-span-2">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
            />

            <input
              type="text"
              value={filters.plate_text}
              onChange={(e) => handlePlateSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder={t("Search plate number...")}
            />
          </div>

          {/* Camera filter */}

          <select
            value={filters.camera_id}
            onChange={(e) => setFilter("camera_id", e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{t("All Cameras")}</option>

            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>
                {c.camera_id}
              </option>
            ))}
          </select>

          {/* Type filter */}

          <select
            value={filters.violation_type}
            onChange={(e) => setFilter("violation_type", e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{t("All Types")}</option>

            <option value="NO_HELMET">{t("No Helmet")}</option>

            <option value="TRIPLE_RIDING">{t("Triple Riding")}</option>

            <option value="CO_RIDING_NO_HELMET">
              {t("Co-rider No Helmet")}
            </option>
          </select>

          {/* Date from */}

          <input
            type="date"
            value={filters.date_from?.split("T")[0] || ""}
            onChange={(e) =>
              setFilter(
                "date_from",
                e.target.value ? e.target.value + "T00:00:00Z" : "",
              )
            }
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />

          {/* Clear */}

          <button
            onClick={clearFilters}
            className="flex items-center justify-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg px-3 py-2 hover:bg-gray-50 transition-colors"
          >
            <X size={14} /> {t("Clear")}
          </button>
        </div>
      </div>

      {/* Loading */}

      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Table */}

      <ViolationTable
        violations={violations}
        onViewEvidence={setSelectedViolation}
        onDelete={handleDelete}
      />

      {/* Pagination */}

      {pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-30 hover:bg-gray-50"
          >
            {t("Prev")}
          </button>

          {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
            const p = i + 1;

            return (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={`px-3 py-1.5 text-sm rounded-lg ${
                  p === page
                    ? "bg-blue-600 text-white"
                    : "border border-gray-300 hover:bg-gray-50"
                }`}
              >
                {p}
              </button>
            );
          })}

          <button
            onClick={() => setPage(Math.min(pages, page + 1))}
            disabled={page === pages}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-30 hover:bg-gray-50"
          >
            {t("Next")}
          </button>
        </div>
      )}

      {/* Total count */}

      <p className="text-xs text-gray-400 text-center">
        {total} {t("total violations")}
      </p>

      {selectedViolation && (
        <EvidenceModal
          violation={selectedViolation}
          onClose={() => setSelectedViolation(null)}
        />
      )}

      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => !deleteLoading && setDeleteTarget(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-md w-full overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-bold text-gray-900">
                  {t("Delete violation?")}
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  {t("This action cannot be undone.")}
                </p>
              </div>
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleteLoading}
                className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-30"
              >
                <X size={18} className="text-gray-500" />
              </button>
            </div>

            <div className="p-5 space-y-3">
              <div className="text-sm text-gray-700">
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">{t("Camera")}</span>
                  <span className="font-medium">
                    {deleteTarget.camera_id || "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">{t("Track")}</span>
                  <span className="font-medium">
                    #{deleteTarget.track_id ?? "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">{t("Type")}</span>
                  <span className="font-medium">
                    {deleteTarget.violation_type?.replace(/_/g, " ") || "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-gray-400">{t("Plate")}</span>
                  <span className="font-mono font-medium">
                    {deleteTarget.plate_text || "UNDETECTED"}
                  </span>
                </div>
              </div>

              {deleteError && (
                <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {deleteError}
                </div>
              )}
            </div>

            <div className="p-5 border-t border-gray-100 flex items-center justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleteLoading}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-30"
              >
                {t("Cancel")}
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteLoading}
                className="px-3 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteLoading ? t("Deleting…") : t("Delete")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
