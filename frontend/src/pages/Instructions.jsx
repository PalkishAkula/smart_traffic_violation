import { useTranslation } from "react-i18next";

export default function Instructions() {
  const { t } = useTranslation();

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-8">
      <h1 className="text-3xl font-bold text-gray-900">{t("Instructions")}</h1>
      <p className="text-gray-600 text-lg">
        {t(
          "Welcome to the Drive Defender system. Please follow the instructions below to use the application effectively.",
        )}
      </p>

      <div className="space-y-6 mt-8">
        <section className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            {t("1. Creating an Account")}
          </h2>
          <p className="text-gray-600 mb-3">
            {t(
              "To access the core features of the system, you need to create an account.",
            )}
          </p>
          <ul className="list-disc list-inside text-gray-600 space-y-2 ml-2">
            <li>
              {t(
                "Click on the 'Login' button in the top right corner of the navigation bar.",
              )}
            </li>
            <li>{t("Select 'Don't have an account? Register'.")}</li>
            <li>{t("Fill in your name, email, and password to register.")}</li>
          </ul>
        </section>

        <section className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            {t("2. Adding Cameras")}
          </h2>
          <p className="text-gray-600 mb-3">
            {t(
              "Once logged in, you can add traffic cameras to monitor for violations.",
            )}
          </p>
          <ul className="list-disc list-inside text-gray-600 space-y-2 ml-2">
            <li>{t("Navigate to the 'Cameras' page using the menu.")}</li>
            <li>
              {t(
                "Click 'Add Camera' and provide a Camera ID, Location, and Source.",
              )}
            </li>
            <li>
              {t(
                "For Source, you can use an RTSP URL for IP cameras, or '0' for your local webcam.",
              )}
            </li>
            <li>
              {t("The system will start analyzing the live feed immediately.")}
            </li>
          </ul>
        </section>

        <section className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            {t("3. Uploading Videos")}
          </h2>
          <p className="text-gray-600 mb-3">
            {t(
              "You can also upload pre-recorded videos for violation detection if you don't have a live camera.",
            )}
          </p>
          <ul className="list-disc list-inside text-gray-600 space-y-2 ml-2">
            <li>{t("Go to the 'Upload' page.")}</li>
            <li>
              {t(
                "Drag and drop your video file (supports MP4, AVI, MOV, MKV up to 500MB).",
              )}
            </li>
            <li>
              {t(
                "Click 'Start Processing' and wait for the AI to analyze the video frames.",
              )}
            </li>
            <li>
              {t(
                "View the detailed detection results and statistics upon completion.",
              )}
            </li>
          </ul>
        </section>

        <section className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            {t("4. Managing Violations & Evidence")}
          </h2>
          <p className="text-gray-600 mb-3">
            {t(
              "All detected violations are securely logged and can be reviewed at any time.",
            )}
          </p>
          <ul className="list-disc list-inside text-gray-600 space-y-2 ml-2">
            <li>
              {t(
                "Visit the 'Violations' page to see a comprehensive list of all infractions.",
              )}
            </li>
            <li>
              {t(
                "Use the filters at the top to search by license plate, camera ID, date range, or violation type (e.g., No Helmet, Triple Riding).",
              )}
            </li>
            <li>
              {t(
                "Click on the evidence thumbnail image to view a larger version in the Evidence Modal.",
              )}
            </li>
            <li>
              {t(
                "You can export the filtered violations data to a CSV file for reporting purposes.",
              )}
            </li>
          </ul>
        </section>

        <section className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm flex items-center bg-blue-50/50">
          <div className="w-12 h-12 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center mr-4 flex-shrink-0">
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900">
              {t("Need more help?")}
            </h3>
            <p className="text-sm text-gray-600">
              {t(
                "Ensure your backend server and ML models are running for the system to function correctly. Check the top right corner for real-time notifications.",
              )}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
