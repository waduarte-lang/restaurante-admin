import { useState, useEffect, useCallback } from 'react'
import { ChevronRight, ChevronDown, ChevronUp, Search, FileDown, X } from 'lucide-react'
import { crmApi } from '../api/index'

interface Pedido {
  id: number
  order_number?: string
  status?: string
  customer_name?: string
  product_name?: string
  product_sku?: string
  quantity_to_produce?: number
  quantity_produced?: number
  sales_order_number?: string
  sales_order_delivery_date?: string
  created_at?: string
  avance_pct?: number
  area_name?: string
}

const STATUS_LABELS: Record<string, string> = {
  en_proceso:  'En Proceso',
  programada:  'Programada',
  pausada:     'Pausada',
  terminada:   'Terminada',
  cancelada:   'Cancelada',
}

const STATUS_COLORS: Record<string, string> = {
  en_proceso: 'bg-blue-100 text-blue-700',
  programada: 'bg-yellow-100 text-yellow-700',
  pausada:    'bg-orange-100 text-orange-700',
  terminada:  'bg-green-100 text-green-700',
  cancelada:  'bg-red-100 text-red-700',
}

const STATUS_ORDER = ['en_proceso', 'programada', 'pausada', 'terminada', 'cancelada']

function fmtDate(s?: string) {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-900 font-medium text-right max-w-[60%] truncate">{value ?? '—'}</span>
    </div>
  )
}

function PedidoCard({ p, onClick }: { p: Pedido; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full bg-white rounded-xl p-4 shadow-sm border border-gray-100 text-left active:bg-gray-50">
      <div className="flex items-start justify-between mb-1">
        <span className="font-semibold text-gray-900 text-sm">{p.order_number ?? `OP-${p.id}`}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[p.status ?? ''] ?? 'bg-gray-100 text-gray-600'}`}>
          {STATUS_LABELS[p.status ?? ''] ?? p.status ?? '—'}
        </span>
      </div>
      <p className="text-sm text-gray-700 font-medium truncate">{p.product_name ?? '—'}</p>
      {p.product_sku && <p className="text-xs text-gray-400">SKU: {p.product_sku}</p>}
      <p className="text-xs text-gray-500 mt-1">Cliente: {p.customer_name ?? '—'}</p>
      {p.avance_pct != null && (
        <div className="mt-2">
          <div className="flex justify-between text-xs text-gray-500 mb-0.5">
            <span>Avance</span><span>{p.avance_pct}%</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${Math.min(p.avance_pct, 100)}%` }} />
          </div>
        </div>
      )}
      <div className="flex justify-between mt-2 text-xs text-gray-400">
        <span>Colocado: {fmtDate(p.created_at)}</span>
        {p.sales_order_delivery_date && <span>Entrega: {fmtDate(p.sales_order_delivery_date)}</span>}
      </div>
    </button>
  )
}

function PedidoDetalle({ pedido, onBack }: { pedido: Pedido; onBack: () => void }) {
  return (
    <div>
      <div className="bg-white px-4 py-3 border-b border-gray-100 flex items-center gap-3">
        <button onClick={onBack} className="text-blue-600 p-1">
          <ChevronRight size={20} className="rotate-180" />
        </button>
        <p className="font-semibold text-gray-900">{pedido.order_number ?? `OP-${pedido.id}`}</p>
      </div>
      <div className="p-4 space-y-3">
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 space-y-2">
          <Row label="Cliente" value={pedido.customer_name} />
          <Row label="Producto" value={pedido.product_name} />
          <Row label="SKU" value={pedido.product_sku} />
          <Row label="Área" value={pedido.area_name} />
          <Row label="Pedido venta" value={pedido.sales_order_number} />
          <Row label="Fecha colocación" value={fmtDate(pedido.created_at)} />
          <Row label="Fecha entrega" value={fmtDate(pedido.sales_order_delivery_date)} />
          <Row label="Cantidad a producir" value={pedido.quantity_to_produce?.toString()} />
          <Row label="Cantidad producida" value={pedido.quantity_produced?.toString()} />
          <Row label="Avance" value={pedido.avance_pct != null ? `${pedido.avance_pct}%` : undefined} />
        </div>
      </div>
    </div>
  )
}

export default function PedidosPage() {
  const [data, setData] = useState<{ items: Pedido[]; total: number }>({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Pedido | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [pdfLoading, setPdfLoading] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 400)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    setLoading(true)
    crmApi.pedidos({ per_page: 100, ...(debouncedQ ? { q: debouncedQ } : {}) })
      .then(d => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [debouncedQ])

  const downloadPDF = useCallback(async () => {
    setPdfLoading(true)
    try {
      const blob = await crmApi.pedidosPDF(debouncedQ ? { q: debouncedQ } : undefined)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'pedidos.pdf'
      a.click()
      URL.revokeObjectURL(url)
    } catch {}
    setPdfLoading(false)
  }, [debouncedQ])

  if (selected) return <PedidoDetalle pedido={selected} onBack={() => setSelected(null)} />

  const grouped = STATUS_ORDER.reduce<Record<string, Pedido[]>>((acc, s) => {
    const items = data.items.filter(p => p.status === s)
    if (items.length) acc[s] = items
    return acc
  }, {})

  return (
    <div className="p-3 space-y-3">
      {/* Search + PDF bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Buscar cliente o producto…"
            className="w-full pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          {q && (
            <button onClick={() => setQ('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400">
              <X size={14} />
            </button>
          )}
        </div>
        <button
          onClick={downloadPDF}
          disabled={pdfLoading}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm font-medium rounded-xl active:bg-blue-700 disabled:opacity-60 whitespace-nowrap"
        >
          <FileDown size={15} />
          {pdfLoading ? '…' : 'PDF'}
        </button>
      </div>

      {loading && (
        <div className="flex justify-center py-10">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}
      {!loading && Object.keys(grouped).length === 0 && (
        <p className="text-center text-gray-400 py-10">
          {debouncedQ ? 'Sin resultados para tu búsqueda' : 'No hay pedidos activos'}
        </p>
      )}
      {!loading && Object.entries(grouped).map(([status, items]) => {
        const isOpen = !collapsed[status]
        return (
          <div key={status}>
            <button
              className="w-full flex items-center justify-between px-1 py-1.5"
              onClick={() => setCollapsed(c => ({ ...c, [status]: !c[status] }))}
            >
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-600'}`}>
                  {STATUS_LABELS[status] ?? status}
                </span>
                <span className="text-xs text-gray-500">{items.length}</span>
              </div>
              {isOpen ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
            </button>
            {isOpen && (
              <div className="space-y-2">
                {items.map(p => <PedidoCard key={p.id} p={p} onClick={() => setSelected(p)} />)}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
