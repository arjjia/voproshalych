import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { DashboardPage } from "@/pages/Dashboard";
import { LoginPage } from "@/pages/Login";
import { QAPairsPage } from "@/pages/QAPairs";
import { UsersPage } from "@/pages/Users";
import { AUTH_CHANGED_EVENT, hasStoredCredentials } from "@/lib/auth";

export function App() {
  const [, forceRerender] = useState(0);

  useEffect(() => {
    const refreshAuthState = () => forceRerender((v) => v + 1);
    window.addEventListener(AUTH_CHANGED_EVENT, refreshAuthState);
    window.addEventListener("storage", refreshAuthState);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, refreshAuthState);
      window.removeEventListener("storage", refreshAuthState);
    };
  }, []);

  const isAuthenticated = hasStoredCredentials();

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
        />
        <Route
          element={isAuthenticated ? <AppLayout /> : <Navigate to="/login" replace />}
        >
          <Route index element={<DashboardPage />} />
          <Route path="/qa" element={<QAPairsPage />} />
          <Route path="/users" element={<UsersPage />} />
        </Route>
        <Route path="*" element={<Navigate to={isAuthenticated ? "/" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
