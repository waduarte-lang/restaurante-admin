import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { paymentsApi, ordersApi, reportsApi } from '../../api'
import { CashRegister, Order } from '../../types'
import toast from 'react-hot-toast'
import { DollarSign, X } from 'lucide-react'

export default function CajaPage() {
  const qc = useQueryClient()
  const [payModal, setPayModal] = useState<Order | null>(null)
  const [fondoInicial, setFondoInicial] = useState(0)

  const today = new Date().toISOString().split('T')[0]

  const { data: activeCaja, error: cajaError } = useQuery<CashRegister>({
    queryKey: ['active-caja'],
    queryFn: paymentsApi.activeCashRegister,
    retry: false,
  })

  const { data: readyOrders = [] } = useQuery<Order[]>({
    queryKey: ['orders', 'listo'],
    queryFn: () => ordersApi.list('listo'),
  })

  const { data: sales } = useQuery({
    queryKey: ['sales', today],
    queryFn: () => reportsApi.sales(today, today),
    enabled: !!activeCaja,
  })

  const openCajaMutation = useMutation({
    mutationFn: (data: object) => paymentsApi.openRegister(data),
    onSuccess: () => { toast.success('Caja abierta'); qc.invalidateQueries({ queryKey: ['active-caja'] }) },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error'),
  })

  const closeCajaMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) => paymentsApi.closeRegister(id, data),
    onSuccess: () => { toast.success('Caja cerrada'); qc.invalidateQueries({ queryKey: ['active-caja'] }) },
  })

  if (!activeCaja && !cajaError) return <div className="p-6 text-gray-500">Cargando...</div>

  if (!activeCaja) {
    return (
      <div className="p-6 flex items-center justify-center min-h-96">
        <div className="card max-w-sm w-full text-center">
          <DollarSign className="mx-auto text-orange-400 mb-3" size={40} />
          <h2 className="text-xl font-bold text-gray-900 mb-2">Abrir Caja</h2>
          <p className="text-gray-500 text-sm mb-4">Ingresa el fondo inicial para comenzar el turno</p>
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1 text-left">Fondo inicial</label>
            <input type="number" className="input" value={fondoInicial} onChange={e => setFondoInicial(Number(e.target.value))} />
          </div>
          <button onClick={() => openCajaMutation.mutate({ fondo_inicial: fondoInicial })} className="btn-primary w-full">
            Abrir caja
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Caja</h1>
          <p className="text-gray-500 text-sm">Caja abierta desde {new Date(activeCaja.apertura).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}</p>
        </div>
        <button
          onClick={() => closeCajaMutation.mutate({ id: activeCaja.id, data: { total_final: sales?.total_ventas || 0 } })}
          className="btn-danger"
        >
          Cerrar caja
        </button>
      </div>

      {sales && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Ventas totales', value: `$${sales.total_ventas.toLocaleString()}` },
            { label: 'Pedidos cobrados', value: sales.cantidad_pedidos },
            { label: 'Ticket promedio', value: `$${sales.ticket_promedio}` },
            { label: 'Fondo inicial', value: `$${activeCaja.fondo_inicial}` },
          ].map(({ label, value }) => (
            <div key={label} className="card">
              <p className="text-xs text-gray-500">{label}</p>
              <p className="text-xl font-bold text-gray-900 mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      {sales && Object.keys(sales.por_metodo_pago || {}).length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-gray-800 mb-3">Ventas por método de pago</h2>
          <div className="flex gap-6">
            {Object.entries(sales.por_metodo_pago).map(([metodo, total]) => (
              <div key={metodo}>
                <p className="text-xs text-gray-500 capitalize">{metodo}</p>
                <p className="text-lg font-bold text-gray-900">${(total as number).toFixed(2)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h2 className="font-semibold text-gray-800 mb-4">Pedidos listos para cobrar ({readyOrders.length})</h2>
        {readyOrders.length === 0 ? (
          <p className="text-gray-400 text-sm">No hay pedidos listos para cobrar</p>
        ) : (
          <div className="space-y-2">
            {readyOrders.map((order: Order) => (
              <div key={order.id} className="flex items-center justify-between p-3 border border-gray-200 rounded-lg">
                <div>
                  <span className="font-medium text-sm">Mesa {order.mesa_id} — Pedido #{order.id}</span>
                  <span className="text-xs text-gray-500 ml-2">{order.items.length} ítems</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-bold text-gray-900">${order.total.toFixed(2)}</span>
                  <button onClick={() => setPayModal(order)} className="btn-primary text-sm py-1.5">Cobrar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {payModal && (
        <PaymentModal
          order={payModal}
          cajaId={activeCaja.id}
          onClose={() => setPayModal(null)}
          onSuccess={() => {
            setPayModal(null)
            qc.invalidateQueries({ queryKey: ['orders'] })
            qc.invalidateQueries({ queryKey: ['sales'] })
            qc.invalidateQueries({ queryKey: ['tables'] })
          }}
        />
      )}
    </div>
  )
}

function PaymentModal({ order, cajaId, onClose, onSuccess }: {
  order: Order; cajaId: number; onClose: () => void; onSuccess: () => void
}) {
  const [metodo, setMetodo] = useState('efectivo')
  const [monto, setMonto] = useState(order.total)

  const mutation = useMutation({
    mutationFn: (data: object) => paymentsApi.create(data),
    onSuccess: () => { toast.success('Pago registrado'); onSuccess() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error'),
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-gray-900">Cobrar pedido #{order.id}</h2>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>
        <p className="text-2xl font-bold text-gray-900 mb-4">Total: ${order.total.toFixed(2)}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Método de pago</label>
            <div className="flex gap-2">
              {['efectivo', 'tarjeta', 'transferencia'].map(m => (
                <button key={m} onClick={() => setMetodo(m)} className={`flex-1 py-2 rounded-lg border-2 text-sm font-medium capitalize transition-colors ${metodo === m ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-600'}`}>
                  {m}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Monto recibido</label>
            <input type="number" className="input" value={monto} onChange={e => setMonto(Number(e.target.value))} />
          </div>
          {metodo === 'efectivo' && monto >= order.total && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3">
              <p className="text-sm text-green-700 font-medium">Cambio: ${(monto - order.total).toFixed(2)}</p>
            </div>
          )}
        </div>
        <div className="flex gap-3 mt-5">
          <button onClick={onClose} className="btn-secondary flex-1">Cancelar</button>
          <button onClick={() => mutation.mutate({ order_id: order.id, monto: order.total, metodo, caja_id: cajaId })} disabled={mutation.isPending} className="btn-primary flex-1">
            Confirmar pago
          </button>
        </div>
      </div>
    </div>
  )
}
