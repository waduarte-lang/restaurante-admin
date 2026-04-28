import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import Layout from './components/Layout'
import LoginPage from './pages/Login/LoginPage'
import DashboardPage from './pages/Dashboard/DashboardPage'
import MesasPage from './pages/Mesas/MesasPage'
import InventarioPage from './pages/Inventario/InventarioPage'
import CajaPage from './pages/Caja/CajaPage'
import CostosPage from './pages/Costos/CostosPage'
import AdminPage from './pages/Admin/AdminPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  const { token } = useAuthStore()
  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="mesas" element={<MesasPage />} />
        <Route path="inventario" element={<InventarioPage />} />
        <Route path="caja" element={<CajaPage />} />
        <Route path="costos" element={<CostosPage />} />
        <Route path="admin" element={<AdminPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
