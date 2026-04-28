import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "../shared/auth/AuthProvider";
import { AdminLayout } from "./layouts/AdminLayout";
import { LoginPage } from "../features/auth/LoginPage";
import { PlaygroundPage } from "../features/playground/PlaygroundPage";
import { SandboxImagesPage } from "../features/sandbox-images/SandboxImagesPage";
import { SystemUsersPage } from "../features/system-users/SystemUsersPage";
import { WorkProjectsPage } from "../features/work-projects/WorkProjectsPage";

function ProtectedRoute() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

function PublicOnlyRoute() {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/system-users" replace />;
  }

  return <Outlet />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<AdminLayout />}>
              <Route index element={<Navigate to="/system-users" replace />} />
              <Route path="/playground" element={<PlaygroundPage />} />
              <Route path="/sandbox-images" element={<SandboxImagesPage />} />
              <Route path="/system-users" element={<SystemUsersPage />} />
              <Route path="/work-projects" element={<WorkProjectsPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/system-users" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
