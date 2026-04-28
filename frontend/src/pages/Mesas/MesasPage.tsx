import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tablesApi, ordersApi, menuApi } from '../../api'
import { Table, Order, MenuItem, MenuCategory } from '../../types'
import toast from 'react-hot-toast'
import { Plus, X, ChefHat, CheckCircle, CreditCard } from 'lucide-react'

type ModalType = 'order' | 'new_order' | null

export default function MesasPage() {
  const qc = useQueryClient()
  const [selectedTable, setSelectedTable] = useState<Table | null>(null)
  const [modal, setModal] = useState<ModalType>(null)
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null)

  const { data: tables = [] } = useQuery<Table[]>({ queryKey: ['tables'], queryFn: tablesApi.list })
  const { data: menuItems = [] } = useQuery<MenuItem[]>({ queryKey: ['menu-items'], queryFn: () => menuApi.items() })
  const { data: categories = [] } = useQuery<MenuCategory[]>({ queryKey: ['categories'], queryFn: menuApi.categories })
  const { data: orders = [] } = useQuery<Order[]>({ queryKey: ['orders', 'abierto'], queryFn: () => ordersApi.list('abierto') })

  const updateOrderMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) => ordersApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['orders'] }); qc.invalidateQueries({ queryKey: ['tables'] }) },
  })

  const tableOrder = (tableId: number) => orders.find((o: Order) => o.mesa_id === tableId)

  const stateColor = (estado: string) => ({
    libre: 'border-green-300 bg-green-50 hover:bg-green-100',
    ocupada: 'border-red-300 bg-red-50 hover:bg-red-100',
    esperando_pago: 'border-yellow-300 bg-yellow-50 hover:bg-yellow-100',
  }[estado] || 'border-gray-200 bg-white')

  const handleTableClick = (table: Table) => {
    setSelectedTable(table)
    const order = tableOrder(table.id)
    if (order) { setSelectedOrder(order); setModal('order') }
    else setModal('new_order')
  }

  const handleSendToKitchen = (orderId: number) => {
    updateOrderMutation.mutate({ id: orderId, data: { estado: 'en_cocina' } }, {
      onSuccess: () => { toast.success('Pedido enviado a cocina'); setModal(null) }
    })
  }

  const handleMarkReady = (orderId: number) => {
    updateOrderMutation.mutate({ id: orderId, data: { estado: 'listo' } }, {
      onSuccess: () => { toast.success('Pedido listo'); setModal(null) }
    })
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Mesas</h1>
          <p className="text-gray-500 text-sm">Selecciona una mesa para gestionar pedidos</p>
        </div>
        <div className="flex gap-3 text-xs">
          {[['bg-green-100 border-green-300', 'Libre'], ['bg-red-100 border-red-300', 'Ocupada'], ['bg-yellow-100 border-yellow-300', 'Esperando pago']].map(([cls, label]) => (
            <span key={label} className={`border px-3 py-1 rounded-full ${cls}`}>{label}</span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-4">
        {tables.map((table) => {
          const order = tableOrder(table.id)
          return (
            <button
              key={table.id}
              onClick={() => handleTableClick(table)}
              className={`border-2 rounded-xl p-4 text-center transition-all cursor-pointer ${stateColor(table.estado)}`}
            >
              <div className="text-2xl font-bold text-gray-800">{table.numero}</div>
              <div className="text-xs text-gray-500 mt-1">{table.capacidad} personas</div>
              {order && <div className="text-xs font-medium text-gray-600 mt-1">${order.total}</div>}
              <div className={`text-xs mt-2 capitalize ${table.estado === 'libre' ? 'text-green-600' : table.estado === 'ocupada' ? 'text-red-600' : 'text-yellow-600'}`}>
                {table.estado.replace('_', ' ')}
              </div>
            </button>
          )
        })}
      </div>

      {modal === 'order' && selectedOrder && (
        <OrderModal
          order={selectedOrder}
          table={selectedTable!}
          onClose={() => setModal(null)}
          onSendKitchen={() => handleSendToKitchen(selectedOrder.id)}
          onMarkReady={() => handleMarkReady(selectedOrder.id)}
        />
      )}

      {modal === 'new_order' && selectedTable && (
        <NewOrderModal
          table={selectedTable}
          menuItems={menuItems}
          categories={categories}
          onClose={() => setModal(null)}
          onSuccess={() => {
            setModal(null)
            qc.invalidateQueries({ queryKey: ['orders'] })
            qc.invalidateQueries({ queryKey: ['tables'] })
          }}
        />
      )}
    </div>
  )
}

function OrderModal({ order, table, onClose, onSendKitchen, onMarkReady }: {
  order: Order; table: Table; onClose: () => void
  onSendKitchen: () => void; onMarkReady: () => void
}) {
  const estadoLabel = { abierto: 'Abierto', en_cocina: 'En cocina', listo: 'Listo para servir', pagado: 'Pagado' }
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b">
          <div>
            <h2 className="font-bold text-gray-900">Mesa {table.numero} — Pedido #{order.id}</h2>
            <span className="text-xs text-gray-500">{estadoLabel[order.estado as keyof typeof estadoLabel]}</span>
          </div>
          <button onClick={onClose}><X size={20} className="text-gray-400 hover:text-gray-600" /></button>
        </div>
        <div className="p-5 space-y-2 max-h-72 overflow-y-auto">
          {order.items.map(item => (
            <div key={item.id} className="flex justify-between text-sm">
              <span>{item.cantidad}x {item.item_nombre}</span>
              <span className="text-gray-500">${(item.cantidad * item.precio_unitario).toFixed(2)}</span>
            </div>
          ))}
        </div>
        <div className="px-5 py-3 bg-gray-50 rounded-b-2xl flex items-center justify-between">
          <span className="font-bold text-gray-900">Total: ${order.total.toFixed(2)}</span>
          <div className="flex gap-2">
            {order.estado === 'abierto' && (
              <button onClick={onSendKitchen} className="btn-primary flex items-center gap-1 text-sm py-1.5">
                <ChefHat size={15} /> Enviar
              </button>
            )}
            {order.estado === 'en_cocina' && (
              <button onClick={onMarkReady} className="btn-primary flex items-center gap-1 text-sm py-1.5">
                <CheckCircle size={15} /> Listo
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function NewOrderModal({ table, menuItems, categories, onClose, onSuccess }: {
  table: Table; menuItems: MenuItem[]; categories: MenuCategory[]
  onClose: () => void; onSuccess: () => void
}) {
  const [items, setItems] = useState<{ item_id: number; cantidad: number; nombre: string; precio: number }[]>([])
  const [activecat, setActiveCat] = useState<number | null>(null)
  const qc = useQueryClient()

  const createOrder = useMutation({
    mutationFn: (data: object) => ordersApi.create(data),
    onSuccess: () => { toast.success('Pedido creado'); onSuccess() },
    onError: () => toast.error('Error al crear pedido'),
  })

  const filteredItems = activecat ? menuItems.filter(m => m.categoria_id === activecat) : menuItems

  const addItem = (item: MenuItem) => {
    setItems(prev => {
      const existing = prev.find(i => i.item_id === item.id)
      if (existing) return prev.map(i => i.item_id === item.id ? { ...i, cantidad: i.cantidad + 1 } : i)
      return [...prev, { item_id: item.id, cantidad: 1, nombre: item.nombre, precio: item.precio }]
    })
  }

  const removeItem = (item_id: number) => setItems(prev => prev.filter(i => i.item_id !== item_id))

  const total = items.reduce((acc, i) => acc + i.precio * i.cantidad, 0)

  const handleSubmit = () => {
    if (!items.length) { toast.error('Agrega al menos un ítem'); return }
    createOrder.mutate({ mesa_id: table.id, items: items.map(({ item_id, cantidad }) => ({ item_id, cantidad })) })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-5 border-b">
          <h2 className="font-bold text-gray-900">Nuevo Pedido — Mesa {table.numero}</h2>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4">
            <div className="flex gap-2 flex-wrap mb-3">
              <button onClick={() => setActiveCat(null)} className={`text-xs px-3 py-1 rounded-full border ${!activecat ? 'bg-orange-500 text-white border-orange-500' : 'border-gray-300'}`}>Todo</button>
              {categories.map(c => (
                <button key={c.id} onClick={() => setActiveCat(c.id)} className={`text-xs px-3 py-1 rounded-full border ${activecat === c.id ? 'bg-orange-500 text-white border-orange-500' : 'border-gray-300'}`}>{c.nombre}</button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2">
              {filteredItems.map(item => (
                <button key={item.id} onClick={() => addItem(item)} className="text-left border rounded-lg p-3 hover:border-orange-400 hover:bg-orange-50 transition-colors">
                  <div className="font-medium text-sm text-gray-800">{item.nombre}</div>
                  <div className="text-xs text-orange-600 font-semibold mt-1">${item.precio}</div>
                </button>
              ))}
            </div>
          </div>
          <div className="w-52 border-l p-4 flex flex-col">
            <h3 className="font-semibold text-sm text-gray-700 mb-3">Pedido</h3>
            <div className="flex-1 overflow-y-auto space-y-2">
              {items.length === 0 && <p className="text-xs text-gray-400">Sin ítems</p>}
              {items.map(item => (
                <div key={item.item_id} className="flex items-center gap-1 text-xs">
                  <span className="flex-1 truncate">{item.cantidad}x {item.nombre}</span>
                  <button onClick={() => removeItem(item.item_id)} className="text-red-400 hover:text-red-600"><X size={13} /></button>
                </div>
              ))}
            </div>
            <div className="border-t pt-3 mt-3">
              <div className="flex justify-between text-sm font-bold mb-3">
                <span>Total</span><span>${total.toFixed(2)}</span>
              </div>
              <button onClick={handleSubmit} disabled={createOrder.isPending} className="btn-primary w-full text-sm py-2">
                {createOrder.isPending ? 'Creando...' : 'Crear pedido'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
