import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./lib/AuthContext";
import { ProtectedRoute, RoleRoute } from "./components/ProtectedRoute";
import { Layout } from "./components/layout/Layout";

import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";
import VerifyEmail from "./pages/auth/VerifyEmail";

import Dashboard from "./pages/Dashboard";
import Entrate from "./pages/Entrate";
import Uscite from "./pages/Uscite";
import Movimenti from "./pages/Movimenti";
import Preventivi from "./pages/Preventivi";
import Bilancio from "./pages/Bilancio";
import Categorie from "./pages/Categorie";
import Utenti from "./pages/Utenti";
import Impostazioni from "./pages/Impostazioni";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/entrate" element={<Entrate />} />
            <Route path="/uscite" element={<Uscite />} />
            <Route path="/preventivi" element={<Preventivi />} />
            <Route path="/movimenti" element={<Movimenti />} />
            <Route path="/bilancio" element={<Bilancio />} />
            <Route path="/categorie" element={<Categorie />} />
            <Route path="/impostazioni" element={<Impostazioni />} />
            <Route element={<RoleRoute roles={["ADMIN"]} />}>
              <Route path="/utenti" element={<Utenti />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
