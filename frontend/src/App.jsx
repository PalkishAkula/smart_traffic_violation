import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import Navbar from "./components/Navbar";
import ViolationToast from "./components/ViolationToast";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import Cameras from "./pages/Cameras";
import Upload from "./pages/Upload";
import Violations from "./pages/Violations";
import Instructions from "./pages/Instructions";
import socket, { connectSocket } from "./services/socket";
import api from "./services/api";

function ProtectedRoute({ children }) {
  const token = localStorage.getItem("access_token");
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

function AppLayout({ children, toasts, dismissToast, fullWidth = false }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className={fullWidth ? "w-full" : "max-w-7xl mx-auto px-6 py-6"}>
        {children}
      </main>

      {/* Global violation toasts */}
      <div className="fixed top-20 right-6 z-50 space-y-2">
        {toasts.map((t) => (
          <ViolationToast
            key={t.id}
            violation={t}
            onDismiss={() => dismissToast(t.id)}
          />
        ))}
      </div>
    </div>
  );
}

/* ── Loading screen shown while ML models load at startup ─────────── */
function ModelLoadingScreen() {
  return (
    <div className="fixed inset-0 bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center z-[100]">
      <div className="text-center space-y-6">
        {/* Animated ring */}
        <div className="relative w-20 h-20 mx-auto">
          <div className="absolute inset-0 border-4 border-blue-500/20 rounded-full" />
          <div className="absolute inset-0 border-4 border-transparent border-t-blue-500 rounded-full animate-spin" />
          <div
            className="absolute inset-2 border-4 border-transparent border-t-cyan-400 rounded-full animate-spin"
            style={{ animationDirection: "reverse", animationDuration: "1.5s" }}
          />
        </div>

        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            Loading Detection Models
          </h2>
          <p className="text-sm text-blue-300/70 mt-2 max-w-xs mx-auto">
            Loading YOLO and OCR models. This only happens once when the server
            starts.
          </p>
        </div>

        {/* Pulsing dots */}
        <div className="flex justify-center gap-1.5">
          <div
            className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"
            style={{ animationDelay: "0s" }}
          />
          <div
            className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"
            style={{ animationDelay: "0.2s" }}
          />
          <div
            className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"
            style={{ animationDelay: "0.4s" }}
          />
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [toasts, setToasts] = useState([]);
  const [modelsReady, setModelsReady] = useState(false);

  // Poll /api/health until models are loaded
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get("/api/health");
        if (res.data.models_loaded === true) {
          setModelsReady(true);
          clearInterval(interval);
        }
      } catch {
        // Server not ready yet — keep polling
      }
    }, 2000);

    // Also check immediately
    api
      .get("/api/health")
      .then((res) => {
        if (res.data?.models_loaded === true) {
          setModelsReady(true);
          clearInterval(interval);
        }
      })
      .catch(() => {});

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Connect socket and listen for real-time violations
    connectSocket();

    const handleViolation = (data) => {
      const toast = { ...data, id: Date.now() + Math.random() };
      setToasts((prev) => [...prev.slice(-4), toast]); // Keep last 5
    };

    socket.on("violation", handleViolation);
    return () => socket.off("violation", handleViolation);
  }, []);

  const dismissToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <BrowserRouter>
      {/* Show loading screen until models are ready */}
      {!modelsReady && <ModelLoadingScreen />}

      <Routes>
        <Route
          path="/"
          element={
            <AppLayout toasts={toasts} dismissToast={dismissToast} fullWidth>
              <Home />
            </AppLayout>
          }
        />
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <AppLayout toasts={toasts} dismissToast={dismissToast}>
                <Dashboard />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/cameras"
          element={
            <ProtectedRoute>
              <AppLayout toasts={toasts} dismissToast={dismissToast}>
                <Cameras />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/upload"
          element={
            <ProtectedRoute>
              <AppLayout toasts={toasts} dismissToast={dismissToast}>
                <Upload />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/instructions"
          element={
            <ProtectedRoute>
              <AppLayout toasts={toasts} dismissToast={dismissToast}>
                <Instructions />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/violations"
          element={
            <ProtectedRoute>
              <AppLayout toasts={toasts} dismissToast={dismissToast}>
                <Violations />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
