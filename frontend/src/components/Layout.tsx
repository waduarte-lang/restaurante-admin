import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import {
  LayoutDashboard, UtensilsCrossed, Package, DollarSign,
  TrendingUp, Settings, LogOut, ChefHat
} from 'lucide-react'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', roles: ['admin', 'cajero', 'mesero', 'cocinero'] },
  { to: '/mesas', icon: UtensilsCrossed, label: 'Mesas', roles: ['admin', 'cajero', 'mesero', 'cocinero'] },
  { to: '/inventario', icon: Package, label: 'Inventario', roles: ['admin', 'cajero'] },
  { to: '/caja', icon: DollarSign, label: 'Caja', roles: ['admin', 'cajero'] },
  { to: '/costos', icon: TrendingUp, label: 'Finanzas', roles: ['admin'] },
  { to: '/admin', icon: Settings, label: 'Admin', roles: ['admin'] },
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-56 bg-gray-900 text-white flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <ChefHat className="text-orange-400" size={22} />
            <span className="font-bold text-sm">RestAdmin</span>
          </div>
          <p className="text-xs text-gray-400 mt-1 truncate">{user?.nombre}</p>
          <span className="text-xs bg-orange-500/20 text-orange-300 px-2 py-0.5 rounded-full capitalize">
            {user?.rol}
          </span>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems
            .filter(item => item.roles.includes(user?.rol || ''))
            .map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    isActive
                      ? 'bg-orange-500 text-white'
                      : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                  }`
                }
              >
                <Icon size={17} />
                {label}
              </NavLink>
            ))}
        </nav>
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-6 py-4 text-sm text-gray-400 hover:text-white border-t border-gray-700 transition-colors"
        >
          <LogOut size={17} />
          Cerrar sesión
        </button>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
