import { useQuery } from '@tanstack/react-query'
import { reportsApi, tablesApi, ordersApi } from '../../api'
import { DollarSign, ShoppingBag, Table2, AlertTriangle } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useAuthStore } from '../../store/authStore'

function StatCard({ icon: Icon, label, value, color }: { icon: any, label: string, value: string | number, color: string }) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
        <Icon size={22} className="text-white" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { user } = useAuthStore()
  const today = new Date().toISOString().split('T')[0]

  const { data: sales } = useQuery({
    queryKey: ['sales', today],
    queryFn: () => reportsApi.sales(today, today),
    enabled: ['admin', 'cajero'].includes(user?.rol || ''),
  })

  const { data: tables } = useQuery({ queryKey: ['tables'], queryFn: tablesApi.list })
  const { data: openOrders } = useQuery({ queryKey: ['orders', 'abierto'], queryFn: () => ordersApi.list('abierto') })
  const { data: kitchenOrders } = useQuery({ queryKey: ['orders', 'en_cocina'], queryFn: () => ordersApi.list('en_cocina') })

  const ocupadas = (tables || []).filter((t: any) => t.estado !== 'libre').length
  const totalMesas = (tables || []).length

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm">Resumen del día — {new Date().toLocaleDateString('es', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {sales && (
          <>
            <StatCard icon={DollarSign} label="Ventas del día" value={`$${sales.total_ventas.toLocaleString()}`} color="bg-green-500" />
            <StatCard icon={ShoppingBag} label="Pedidos pagados" value={sales.cantidad_pedidos} color="bg-blue-500" />
          </>
        )}
        <StatCard icon={Table2} label="Mesas ocupadas" value={`${ocupadas} / ${totalMesas}`} color="bg-orange-500" />
        <StatCard icon={AlertTriangle} label="En cocina" value={(kitchenOrders || []).length} color="bg-red-500" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {sales && (
          <div className="card">
            <h2 className="font-semibold text-gray-800 mb-4">Ventas por método de pago</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={Object.entries(sales.por_metodo_pago || {}).map(([k, v]) => ({ metodo: k, total: v }))}>
                <XAxis dataKey="metodo" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v: any) => [`$${v}`, 'Total']} />
                <Bar dataKey="total" fill="#f97316" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="card">
          <h2 className="font-semibold text-gray-800 mb-4">Pedidos abiertos</h2>
          {(openOrders || []).length === 0 ? (
            <p className="text-gray-400 text-sm">No hay pedidos abiertos</p>
          ) : (
            <div className="space-y-2">
              {(openOrders || []).slice(0, 6).map((o: any) => (
                <div key={o.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                  <span className="text-sm font-medium">Mesa {o.mesa_id} — Pedido #{o.id}</span>
                  <span className="text-sm text-gray-500">${o.total}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
