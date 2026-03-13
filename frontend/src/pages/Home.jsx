import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export default function Home() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col min-h-screen">
      <section className="bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 text-white py-20 px-6">
        <div className="max-w-5xl mx-auto text-center space-y-8">
          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight">
            {t("Drive Defender")}
          </h1>

          <p className="text-xl md:text-2xl text-blue-200 font-light max-w-3xl mx-auto">
            {t("Smart Traffic Violation Detection System")}
          </p>

          <p className="text-lg text-gray-300 max-w-2xl mx-auto">
            {t(
              "Our system uses advanced AI to monitor traffic cameras and automatically detect motorcycle violations such as helmet violations, triple riding, and number plate recognition.",
            )}
          </p>

          <div className="pt-8">
            <Link
              to="/dashboard"
              className="inline-flex items-center px-8 py-3 rounded-full bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-all transform hover:scale-105 shadow-lg shadow-blue-500/30"
            >
              {t("Get Started")}
              <svg
                className="ml-2 w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 7l5 5m0 0l-5 5m5-5H6"
                />
              </svg>
            </Link>
          </div>
        </div>
      </section>

      <section className="py-20 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900">
              {t("How it Works")}
            </h2>
            <div className="w-24 h-1 bg-blue-600 mx-auto mt-4 rounded-full" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div className="p-6 bg-gray-50 rounded-2xl border border-gray-100 hover:shadow-xl transition-shadow text-center">
              <div className="text-blue-600 text-4xl mb-4">📷</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3">
                {t("1. Connect Cameras")}
              </h3>
              <p className="text-gray-600">
                {t(
                  "Add your RTSP IP cameras or upload pre-recorded traffic videos to the system.",
                )}
              </p>
            </div>

            <div className="p-6 bg-gray-50 rounded-2xl border border-gray-100 hover:shadow-xl transition-shadow text-center">
              <div className="text-blue-600 text-4xl mb-4">🤖</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3">
                {t("2. AI Processing")}
              </h3>
              <p className="text-gray-600">
                {t(
                  "Deep learning models analyze frames to detect motorcycles and riders.",
                )}
              </p>
            </div>

            <div className="p-6 bg-gray-50 rounded-2xl border border-gray-100 hover:shadow-xl transition-shadow text-center">
              <div className="text-blue-600 text-4xl mb-4">⚠️</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3">
                {t("3. Detect Violations")}
              </h3>
              <p className="text-gray-600">
                {t(
                  "Detects helmet violations, triple riding, and captures vehicle number plates.",
                )}
              </p>
            </div>

            <div className="p-6 bg-gray-50 rounded-2xl border border-gray-100 hover:shadow-xl transition-shadow text-center">
              <div className="text-blue-600 text-4xl mb-4">📊</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3">
                {t("4. Review & Action")}
              </h3>
              <p className="text-gray-600">
                {t(
                  "Violations are stored and can be reviewed from the dashboard.",
                )}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 px-6 bg-gray-50 border-t border-gray-200">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900">
              {t("Features")}
            </h2>
            <div className="w-24 h-1 bg-blue-600 mx-auto mt-4 rounded-full" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            <Link
              to="/dashboard"
              className="block p-8 bg-white rounded-2xl shadow-sm hover:shadow-lg transition-all border border-gray-100 group"
            >
              <h3 className="text-2xl font-bold text-gray-900 mb-4 group-hover:text-blue-600">
                {t("Dashboard")} →
              </h3>
              <p className="text-gray-600">
                {t(
                  "View live statistics and recent violations on the dashboard.",
                )}
              </p>
            </Link>

            <Link
              to="/cameras"
              className="block p-8 bg-white rounded-2xl shadow-sm hover:shadow-lg transition-all border border-gray-100 group"
            >
              <h3 className="text-2xl font-bold text-gray-900 mb-4 group-hover:text-blue-600">
                {t("Cameras")} →
              </h3>
              <p className="text-gray-600">
                {t(
                  "Monitor multiple traffic cameras from a centralized system.",
                )}
              </p>
            </Link>

            <Link
              to="/upload"
              className="block p-8 bg-white rounded-2xl shadow-sm hover:shadow-lg transition-all border border-gray-100 group"
            >
              <h3 className="text-2xl font-bold text-gray-900 mb-4 group-hover:text-blue-600">
                {t("Upload")} →
              </h3>
              <p className="text-gray-600">
                {t(
                  "Upload traffic videos to detect motorcycle violations automatically.",
                )}
              </p>
            </Link>

            <Link
              to="/violations"
              className="block p-8 bg-white rounded-2xl shadow-sm hover:shadow-lg transition-all border border-gray-100 group"
            >
              <h3 className="text-2xl font-bold text-gray-900 mb-4 group-hover:text-blue-600">
                {t("Violations")} →
              </h3>
              <p className="text-gray-600">
                {t(
                  "Store and review detected violations with evidence images.",
                )}
              </p>
            </Link>

            <Link
              to="/instructions"
              className="block p-8 bg-white rounded-2xl shadow-sm hover:shadow-lg transition-all border border-gray-100 group lg:col-span-4 md:col-span-2"
            >
              <h3 className="text-2xl font-bold text-gray-900 mb-4 group-hover:text-blue-600">
                {t("Instructions")} →
              </h3>
              <p className="text-gray-600">
                {t(
                  "Step-by-step guide to use the traffic violation detection system.",
                )}
              </p>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
