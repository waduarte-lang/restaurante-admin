import { useState, useEffect, useCallback } from 'react'
import {
  ChevronRight, Users, MapPin, CheckCircle, LayoutGrid,
  Building2, TrendingUp, Search, Package, ChevronDown,
  ChevronUp, UserPlus, X, RefreshCw, Settings, Pencil,
  KeyRound, UserCheck, UserX, Plus
} from 'lucide-react'
import { crmApi } from '../api/index'
import toast from 'react-hot-toast'
import { ClienteDetailView } from './CuentasPage'

// ── Types ──────────────────────────────────────────────────────────────────────

interface TareasPorEtapa {
  prospecto: number; contactado: number; visita_agendada: number
  propuesta: number; negociacion: number; cumplido: number
}
interface MetricasAsesor {
  id: number; nombre: string; username: string
  clientes_activos: number; visitas_mes: number
  tareas_por_etapa: TareasPorEtapa; tareas_ejecutadas: number
  proxima_visita?: string
}
interface Totales {
  clientes_activos: number; visitas_mes: number
  tareas_ejecutadas: number; tareas_por_etapa: TareasPorEtapa
}
interface Asesor { id: number; nombre: string; username: string }
interface ClienteDatha {
  id: number; nombre: string; nit?: string; ciudad?: string
  telefono?: string; email?: string
  crm_id?: number; asesor?: { id: number; nombre: string } | null
}
interface OrdenStatus {
  status: string; total: number; unidades_total: number
  unidades_producidas: number; unidades_defectuosas: number; avance_pct: number
}
interface Orden {
  id: number; order_number: string; status: string; priority: string
  quantity_to_produce: number; quantity_produced: number; quantity_defective: number
  actual_start_date?: string; actual_end_date?: string; delivery_date?: string
  product_name?: string; product_sku?: string; product_color?: string
  machine_name?: string; area_name?: string; customer_name?: string
  sales_order_number?: string; avance_pct: number; notes?: string
}
interface KanbanData { asesor: { id: number; nombre: string }; kanban: Record<string, any[]> }
interface ClientesData { asesor: { id: number; nombre: string }; clientes: any[] }

// ── Constants ──────────────────────────────────────────────────────────────────

const ETAPAS = [
  { id: 'prospecto',       label: 'Prospecto',   color: 'bg-blue-500'   },
  { id: 'contactado',      label: 'Contactado',  color: 'bg-purple-500' },
  { id: 'visita_agendada', label: 'Visita',      color: 'bg-yellow-500' },
  { id: 'propuesta',       label: 'Propuesta',   color: 'bg-orange-500' },
  { id: 'negociacion',     label: 'Negociación', color: 'bg-pink-500'   },
  { id: 'cumplido',        label: 'Cumplido',    color: 'bg-green-500'  },
]

const ETAPAS_KANBAN = [
  { id: 'prospecto',       label: 'Prospecto',       emoji: '🔵', header: 'bg-blue-600'   },
  { id: 'contactado',      label: 'Contactado',      emoji: '📞', header: 'bg-purple-600' },
  { id: 'visita_agendada', label: 'Visita Agendada', emoji: '📅', header: 'bg-yellow-500' },
  { id: 'propuesta',       label: 'Propuesta',       emoji: '📄', header: 'bg-orange-500' },
  { id: 'negociacion',     label: 'Negociación',     emoji: '🤝', header: 'bg-pink-600'   },
  { id: 'cumplido',        label: 'Cumplido',        emoji: '✅', header: 'bg-green-600'  },
]

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  en_proceso: { label: 'En Proceso',  color: 'bg-blue-100 text-blue-800',     dot: 'bg-blue-500'   },
  programada: { label: 'Programada',  color: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-500' },
  pausada:    { label: 'Pausada',     color: 'bg-orange-100 text-orange-800', dot: 'bg-orange-500' },
  terminada:  { label: 'Terminada',   color: 'bg-green-100 text-green-800',   dot: 'bg-green-500'  },
  cancelada:  { label: 'Cancelada',   color: 'bg-red-100 text-red-800',       dot: 'bg-red-500'    },
}

function fmtDate(s?: string) {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
}
function fmtDatetime(s?: string) {
  if (!s) return '—'
  return new Date(s).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

// ── Shared sub-components ──────────────────────────────────────────────────────

function MetricCard({ label, value, icon: Icon, color }: { label: string; value: number | string; icon: any; color: string }) {
  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
      <div className={`w-9 h-9 ${color} rounded-xl flex items-center justify-center mb-2`}>
        <Icon size={18} className="text-white" />
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  )
}

function EtapaBar({ tareas }: { tareas: TareasPorEtapa }) {
  return (
    <div className="flex gap-1 mt-2 flex-wrap">
      {ETAPAS.map(e => {
        const count = tareas[e.id as keyof TareasPorEtapa] ?? 0
        if (!count) return null
        return (
          <span key={e.id} className={`${e.color} text-white text-xs px-1.5 py-0.5 rounded-full font-medium`}>
            {e.label}: {count}
          </span>
        )
      })}
      {Object.values(tareas).every(v => v === 0) && (
        <span className="text-xs text-gray-400">Sin tareas activas</span>
      )}
    </div>
  )
}

function Row({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className={`font-medium ${danger ? 'text-red-600' : 'text-gray-800'}`}>{value}</span>
    </div>
  )
}

// ── Kanban View (read-only) ────────────────────────────────────────────────────

function KanbanAsesorView({ data, onBack }: { data: KanbanData; onBack: () => void }) {
  return (
    <div className="flex flex-col h-full">
      <div className="bg-white px-4 py-3 border-b flex items-center gap-3 flex-shrink-0">
        <button onClick={onBack} className="text-blue-600"><ChevronRight size={20} className="rotate-180" /></button>
        <div>
          <p className="font-bold text-gray-900">Kanban — {data.asesor.nombre}</p>
          <p className="text-xs text-gray-500">Solo lectura</p>
        </div>
      </div>
      <div className="flex-1 overflow-x-auto">
        <div className="flex gap-3 p-3 h-full" style={{ minWidth: `${ETAPAS_KANBAN.length * 220}px` }}>
          {ETAPAS_KANBAN.map(etapa => {
            const tareas = data.kanban[etapa.id] ?? []
            return (
              <div key={etapa.id} className="flex-shrink-0 w-52 flex flex-col">
                <div className={`${etapa.header} text-white rounded-t-xl px-3 py-2 flex items-center justify-between`}>
                  <span className="text-sm font-bold">{etapa.emoji} {etapa.label}</span>
                  <span className="text-xs bg-white/20 rounded-full px-1.5 py-0.5">{tareas.length}</span>
                </div>
                <div className="flex-1 bg-gray-50 rounded-b-xl p-2 space-y-2 min-h-[80px] overflow-y-auto">
                  {tareas.map((t: any) => (
                    <div key={t.id} className="bg-white rounded-lg p-3 shadow-sm border border-gray-100" style={{ borderLeftColor: t.color, borderLeftWidth: 3 }}>
                      <p className={`text-xs font-semibold text-gray-900 ${t.ejecutado ? 'line-through opacity-50' : ''}`}>{t.titulo}</p>
                      {t.cliente_nombre && <p className="text-xs text-blue-600 truncate mt-0.5">🏢 {t.cliente_nombre}</p>}
                      {t.fecha_inicio   && <p className="text-xs text-gray-400 mt-1">📅 {fmtDatetime(t.fecha_inicio)}</p>}
                      {t.ejecutado && <span className="inline-block mt-1 text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full">✓ Ejecutado</span>}
                    </div>
                  ))}
                  {tareas.length === 0 && <p className="text-xs text-gray-400 text-center py-4">Sin tareas</p>}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function ClientesAsesorView({ data, onBack }: { data: ClientesData; onBack: () => void }) {
  const [selectedCliente, setSelectedCliente] = useState<any | null>(null)

  if (selectedCliente) {
    return (
      <ClienteDetailView
        cliente={{ ...selectedCliente, asesor_nombre: data.asesor.nombre }}
        onBack={() => setSelectedCliente(null)}
      />
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white px-4 py-3 border-b flex items-center gap-3 flex-shrink-0">
        <button onClick={onBack} className="text-blue-600"><ChevronRight size={20} className="rotate-180" /></button>
        <div>
          <p className="font-bold text-gray-900">Clientes — {data.asesor.nombre}</p>
          <p className="text-xs text-gray-500">{data.clientes.length} clientes</p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {data.clientes.map((c: any) => (
          <button
            key={c.id}
            onClick={() => setSelectedCliente(c)}
            className="w-full bg-white rounded-xl p-4 shadow-sm border border-gray-100 text-left flex items-center gap-3 active:bg-gray-50"
          >
            <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
              <Building2 size={18} className="text-blue-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-gray-900 truncate">{c.nombre}</p>
              <p className="text-xs text-gray-500">
                {c.nit ? `NIT: ${c.nit}` : c.ciudad ?? 'Sin NIT'}
              </p>
              {!c.ultima_visita && (
                <p className="text-xs text-orange-500">⚠ Sin visitas registradas</p>
              )}
              {c.ultima_visita && (
                <p className="text-xs text-blue-600">Visita: {fmtDate(c.ultima_visita)}</p>
              )}
            </div>
            <ChevronRight size={16} className="text-gray-400 flex-shrink-0" />
          </button>
        ))}
        {data.clientes.length === 0 && <p className="text-center text-gray-400 py-10">Sin clientes asignados</p>}
      </div>
    </div>
  )
}

// ── Modal Asignar Asesor ───────────────────────────────────────────────────────

function AsignarModal({ cliente, asesores, onClose, onSave }: {
  cliente: ClienteDatha; asesores: Asesor[]
  onClose: () => void; onSave: (asesorId: number | null) => void
}) {
  const [sel, setSel] = useState<number | null>(cliente.asesor?.id ?? null)
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    await onSave(sel)
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end justify-center" onClick={onClose}>
      <div className="bg-white rounded-t-2xl w-full max-w-lg p-5 pb-8" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <p className="font-bold text-gray-900">Asignar Asesor</p>
          <button onClick={onClose}><X size={18} className="text-gray-500" /></button>
        </div>
        <p className="text-sm text-blue-800 font-semibold mb-4 truncate">{cliente.nombre}</p>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          <button
            onClick={() => setSel(null)}
            className={`w-full text-left px-3 py-2.5 rounded-xl text-sm border transition-colors ${sel === null ? 'bg-gray-800 text-white border-gray-800' : 'border-gray-200 hover:bg-gray-50'}`}
          >
            Sin asignar
          </button>
          {asesores.map(a => (
            <button
              key={a.id}
              onClick={() => setSel(a.id)}
              className={`w-full text-left px-3 py-2.5 rounded-xl text-sm border transition-colors ${sel === a.id ? 'bg-blue-700 text-white border-blue-700' : 'border-gray-200 hover:bg-gray-50'}`}
            >
              <span className="font-medium">{a.nombre}</span>
              <span className={`text-xs ml-2 ${sel === a.id ? 'text-blue-200' : 'text-gray-400'}`}>@{a.username}</span>
            </button>
          ))}
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-blue-700 text-white font-semibold py-3 rounded-xl disabled:opacity-50"
        >
          {saving ? 'Guardando…' : 'Guardar asignación'}
        </button>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 1 — Resumen Asesores
// ══════════════════════════════════════════════════════════════════════════════

interface CarteraVendedor {
  vendedor: string; total: number; num_facturas: number
  vigente: number; d30: number; d60: number; d90: number; d90_mas: number
}

function fmtM(n: number) {
  if (n === 0) return '$0'
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

function CarteraAsesorBadge({ nombre, carteraMap }: { nombre: string; carteraMap: Map<string, CarteraVendedor> }) {
  // Always do fuzzy search by first+last name prefix to catch typos (JOHANA/JOHANNA)
  const nombreUp = nombre.toUpperCase()
  const [first, last] = nombreUp.split(' ')
  let combined: CarteraVendedor | undefined
  for (const [key, val] of carteraMap) {
    const [kFirst, kLast] = key.split(' ')
    const minLen = Math.min(first.length, kFirst.length) - 1
    const firstMatch = first.slice(0, minLen) === kFirst.slice(0, minLen)
    const lastMatch  = !last || !kLast || kLast === last
    if (firstMatch && lastMatch) {
      if (!combined) combined = { ...val }
      else {
        combined.total += val.total; combined.num_facturas += val.num_facturas
        combined.vigente += val.vigente; combined.d30 += val.d30
        combined.d60 += val.d60; combined.d90 += val.d90; combined.d90_mas += val.d90_mas
      }
    }
  }
  const cv = combined
  if (!cv || cv.total === 0) return <p className="text-xs text-gray-400 mt-1">Sin cartera registrada</p>
  return (
    <div className="mt-2 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-amber-700">Cartera pendiente</span>
        <span className="text-sm font-bold text-amber-800">{fmtM(cv.total)}</span>
      </div>
      <div className="flex gap-1 flex-wrap">
        {cv.vigente > 0 && <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full">Vigente {fmtM(cv.vigente)}</span>}
        {cv.d30     > 0 && <span className="text-[10px] bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded-full">0–30d {fmtM(cv.d30)}</span>}
        {cv.d60     > 0 && <span className="text-[10px] bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded-full">31–60d {fmtM(cv.d60)}</span>}
        {cv.d90     > 0 && <span className="text-[10px] bg-red-100 text-red-600 px-1.5 py-0.5 rounded-full">61–90d {fmtM(cv.d90)}</span>}
        {cv.d90_mas > 0 && <span className="text-[10px] bg-red-200 text-red-800 px-1.5 py-0.5 rounded-full">&gt;90d {fmtM(cv.d90_mas)}</span>}
      </div>
    </div>
  )
}

function TabResumen({ onKanban, onClientes }: { onKanban: (id: number) => void; onClientes: (id: number) => void }) {
  const [data, setData] = useState<{ asesores: MetricasAsesor[]; totales: Totales } | null>(null)
  const [carteraMap, setCarteraMap] = useState<Map<string, CarteraVendedor>>(new Map())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      crmApi.gerenciaResumen(),
      crmApi.carteraResumenVendedores().catch(() => [] as CarteraVendedor[]),
    ]).then(([d, cv]) => {
      setData(d)
      const m = new Map<string, CarteraVendedor>()
      for (const v of cv) {
        const key = v.vendedor.trim().toUpperCase()
        if (key !== 'SIN VENDEDOR') m.set(key, v)
      }
      setCarteraMap(m)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
  if (!data) return null

  const { asesores, totales } = data
  const totalTareas = Object.values(totales.tareas_por_etapa).reduce((s, v) => s + v, 0)

  return (
    <div className="p-3 space-y-4 pb-6">
      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="Clientes asignados"  value={totales.clientes_activos}  icon={Building2}   color="bg-blue-600"   />
        <MetricCard label="Visitas este mes"     value={totales.visitas_mes}       icon={MapPin}      color="bg-purple-600" />
        <MetricCard label="Tareas en pipeline"   value={totalTareas}               icon={TrendingUp}  color="bg-orange-500" />
        <MetricCard label="Tareas ejecutadas"    value={totales.tareas_ejecutadas} icon={CheckCircle} color="bg-green-600"  />
      </div>

      <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
        <p className="text-xs font-semibold text-gray-500 mb-3">PIPELINE CONSOLIDADO</p>
        <div className="space-y-2">
          {ETAPAS.map(e => {
            const count = totales.tareas_por_etapa[e.id as keyof TareasPorEtapa] ?? 0
            const pct = totalTareas ? Math.round((count / totalTareas) * 100) : 0
            return (
              <div key={e.id}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-600">{e.label}</span>
                  <span className="font-semibold text-gray-800">{count}</span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div className={`h-full ${e.color} rounded-full`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <p className="text-xs font-semibold text-gray-500 flex items-center gap-1.5 -mb-2">
        <Users size={12} /> ASESORES ({asesores.length})
      </p>

      {asesores.length === 0 && (
        <div className="bg-white rounded-xl p-6 text-center text-gray-400 text-sm border border-gray-100">
          No hay asesores registrados aún.<br />
          <span className="text-xs">Crea usuarios con rol "asesor" desde el panel Admin.</span>
        </div>
      )}

      {asesores.map(a => {
        const totalA = Object.values(a.tareas_por_etapa).reduce((s, v) => s + v, 0)
        return (
          <div key={a.id} className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="bg-blue-800 px-4 py-3 flex items-center justify-between">
              <div>
                <p className="font-bold text-white">{a.nombre}</p>
                <p className="text-xs text-blue-300">@{a.username}</p>
              </div>
              <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                <span className="text-white font-bold text-lg">{a.nombre[0]}</span>
              </div>
            </div>
            <div className="p-4">
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="text-center"><p className="text-xl font-bold text-gray-900">{a.clientes_activos}</p><p className="text-xs text-gray-500">Clientes</p></div>
                <div className="text-center border-x border-gray-100"><p className="text-xl font-bold text-gray-900">{a.visitas_mes}</p><p className="text-xs text-gray-500">Visitas mes</p></div>
                <div className="text-center"><p className="text-xl font-bold text-gray-900">{a.tareas_ejecutadas}</p><p className="text-xs text-gray-500">Ejecutadas</p></div>
              </div>
              <CarteraAsesorBadge nombre={a.nombre} carteraMap={carteraMap} />
              <p className="text-xs font-semibold text-gray-500 mb-1 mt-3">PIPELINE ({totalA} tareas)</p>
              <EtapaBar tareas={a.tareas_por_etapa} />
              {a.proxima_visita && (
                <div className="mt-3 flex items-center gap-2 text-xs text-blue-700 bg-blue-50 rounded-lg px-3 py-2">
                  <MapPin size={12} /><span>Próxima: <strong>{fmtDatetime(a.proxima_visita)}</strong></span>
                </div>
              )}
              <div className="flex gap-2 mt-3">
                <button onClick={() => onClientes(a.id)} className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50">
                  <Building2 size={13} /> Clientes
                </button>
                <button onClick={() => onKanban(a.id)} className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-blue-700 text-white text-xs font-medium active:bg-blue-800">
                  <LayoutGrid size={13} /> Kanban
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 2 — Clientes DATHA
// ══════════════════════════════════════════════════════════════════════════════

function TabClientes() {
  const [items, setItems] = useState<ClienteDatha[]>([])
  const [total, setTotal] = useState(0)
  const [asesores, setAsesores] = useState<Asesor[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [filtroAsesor, setFiltroAsesor] = useState<number | ''>('')
  const [sinAsignar, setSinAsignar] = useState(false)
  const [page, setPage] = useState(1)
  const [modalCliente, setModalCliente] = useState<ClienteDatha | null>(null)

  const cargar = useCallback(() => {
    setLoading(true)
    const params: any = { page, per_page: 40 }
    if (q) params.q = q
    if (filtroAsesor) params.asesor_id = filtroAsesor
    if (sinAsignar) params.sin_asignar = true
    Promise.all([
      crmApi.gerenciaClientesDatha(params),
      crmApi.gerenciaAsesores(),
    ]).then(([d, a]) => {
      setItems(d.items)
      setTotal(d.total)
      setAsesores(a)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [q, filtroAsesor, sinAsignar, page])

  useEffect(() => { cargar() }, [cargar])

  async function handleAsignar(asesorId: number | null) {
    if (!modalCliente) return
    try {
      await crmApi.gerenciaAsignarAsesor({
        datha_customer_id: modalCliente.id,
        nombre:   modalCliente.nombre,
        nit:      modalCliente.nit,
        ciudad:   modalCliente.ciudad,
        telefono: modalCliente.telefono,
        email:    modalCliente.email,
        asesor_id: asesorId as any,
      })
      toast.success('Asesor asignado correctamente')
      setModalCliente(null)
      cargar()
    } catch {
      toast.error('Error al guardar la asignación')
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 space-y-2 bg-gray-50 border-b flex-shrink-0">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={e => { setQ(e.target.value); setPage(1) }}
            placeholder="Buscar cliente o NIT…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={filtroAsesor}
            onChange={e => { setFiltroAsesor(e.target.value ? Number(e.target.value) : ''); setPage(1) }}
            className="flex-1 text-xs border border-gray-200 rounded-xl px-3 py-2 bg-white"
          >
            <option value="">Todos los asesores</option>
            {asesores.map(a => <option key={a.id} value={a.id}>{a.nombre}</option>)}
          </select>
          <button
            onClick={() => { setSinAsignar(v => !v); setPage(1) }}
            className={`px-3 py-2 rounded-xl text-xs font-medium border transition-colors ${sinAsignar ? 'bg-orange-500 text-white border-orange-500' : 'bg-white text-gray-600 border-gray-200'}`}
          >
            Sin asesor
          </button>
          <button onClick={cargar} className="p-2 rounded-xl border border-gray-200 bg-white text-gray-500">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div className="px-3 py-2 text-xs text-gray-500 bg-white border-b flex-shrink-0">
        {loading ? 'Cargando…' : `${total.toLocaleString()} clientes en DATHA`}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading && <div className="flex justify-center py-10"><div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>}
        {!loading && items.length === 0 && <p className="text-center text-gray-400 py-10">Sin resultados</p>}
        {items.map(c => (
          <div key={c.id} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 truncate">{c.nombre}</p>
                <div className="flex flex-wrap gap-x-3 mt-0.5">
                  {c.nit    && <p className="text-xs text-gray-500">NIT: {c.nit}</p>}
                  {c.ciudad && <p className="text-xs text-gray-400">{c.ciudad}</p>}
                </div>
                <div className="mt-2">
                  {c.asesor ? (
                    <span className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-full">
                      <Users size={10} /> {c.asesor.nombre}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs bg-orange-50 text-orange-600 px-2 py-1 rounded-full">
                      Sin asesor asignado
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setModalCliente(c)}
                className="flex-shrink-0 flex items-center gap-1 text-xs bg-blue-700 text-white px-2.5 py-1.5 rounded-lg active:bg-blue-800"
              >
                <UserPlus size={12} />
                {c.asesor ? 'Cambiar' : 'Asignar'}
              </button>
            </div>
          </div>
        ))}

        {total > 40 && !loading && (
          <div className="flex items-center justify-center gap-3 pt-2 pb-4">
            <button disabled={page === 1} onClick={() => setPage(p => p - 1)} className="px-3 py-1.5 text-xs border rounded-lg disabled:opacity-40">Anterior</button>
            <span className="text-xs text-gray-500">Página {page} / {Math.ceil(total / 40)}</span>
            <button disabled={items.length < 40} onClick={() => setPage(p => p + 1)} className="px-3 py-1.5 text-xs border rounded-lg disabled:opacity-40">Siguiente</button>
          </div>
        )}
      </div>

      {modalCliente && (
        <AsignarModal
          cliente={modalCliente}
          asesores={asesores}
          onClose={() => setModalCliente(null)}
          onSave={handleAsignar}
        />
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 3 — Producción
// ══════════════════════════════════════════════════════════════════════════════

function TabProduccion() {
  const [resumen, setResumen] = useState<{ por_status: OrdenStatus[]; total_clientes_activos: number } | null>(null)
  const [ordenes, setOrdenes] = useState<Orden[]>([])
  const [total, setTotal] = useState(0)
  const [estadoSel, setEstadoSel] = useState<string | null>('en_proceso')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [loadingRes, setLoadingRes] = useState(true)
  const [loadingOrd, setLoadingOrd] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)

  useEffect(() => {
    crmApi.gerenciaOrdenesResumen().then(setResumen).catch(() => {}).finally(() => setLoadingRes(false))
  }, [])

  useEffect(() => {
    setLoadingOrd(true)
    const params: any = { page, per_page: 50 }
    if (estadoSel) params.estado = estadoSel
    if (q) params.q = q
    crmApi.gerenciaOrdenes(params)
      .then(d => { setOrdenes(d.items); setTotal(d.total) })
      .catch(() => {})
      .finally(() => setLoadingOrd(false))
  }, [estadoSel, q, page])

  const cfg = (s: string) => STATUS_CONFIG[s] ?? { label: s, color: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Buscador fijo en la parte superior */}
      <div className="px-3 pt-3 pb-2 space-y-2 flex-shrink-0 bg-gray-50 border-b border-gray-100">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={e => { setQ(e.target.value); setPage(1) }}
            placeholder="Buscar por cliente, producto u orden…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        {(estadoSel || q) && (
          <div className="flex items-center gap-2 flex-wrap">
            {estadoSel && (
              <div className="flex items-center gap-1">
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${cfg(estadoSel).color}`}>
                  {cfg(estadoSel).label}
                </span>
                <button onClick={() => { setEstadoSel(null); setPage(1) }}><X size={14} className="text-gray-400" /></button>
              </div>
            )}
            {q && (
              <div className="flex items-center gap-1">
                <span className="text-xs px-2 py-1 rounded-full font-medium bg-gray-100 text-gray-600">"{q}"</span>
                <button onClick={() => { setQ(''); setPage(1) }}><X size={14} className="text-gray-400" /></button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Todo el contenido en un solo scroll */}
      <div className="flex-1 overflow-y-auto px-3 pb-6 space-y-2 pt-3">
        {/* Resumen por status — tarjetas clickeables */}
        <p className="text-xs font-semibold text-gray-500">ÓRDENES POR ESTADO</p>
        {loadingRes && <div className="flex justify-center py-6"><div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>}
        {resumen && resumen.por_status.map(s => {
          const c = cfg(s.status)
          const isActive = estadoSel === s.status
          return (
            <button
              key={s.status}
              onClick={() => { setEstadoSel(isActive ? null : s.status); setPage(1) }}
              className={`w-full text-left bg-white rounded-xl p-3 shadow-sm border transition-all ${isActive ? 'border-blue-500 ring-1 ring-blue-300' : 'border-gray-100'}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${c.dot}`} />
                  <span className="text-sm font-bold text-gray-900">{c.label}</span>
                </div>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${c.color}`}>{s.total} órdenes</span>
              </div>
              <div className="flex gap-4 text-xs text-gray-500 mb-1.5">
                <span>Unid. programadas: <strong className="text-gray-700">{Number(s.unidades_total || 0).toLocaleString()}</strong></span>
                <span>Producidas: <strong className="text-gray-700">{Number(s.unidades_producidas || 0).toLocaleString()}</strong></span>
              </div>
              {(s.status === 'en_proceso' || s.status === 'programada') && (
                <>
                  <div className="flex justify-between text-xs mb-0.5">
                    <span className="text-gray-400">Avance</span>
                    <span className="font-semibold text-blue-700">{s.avance_pct}%</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full ${c.dot} rounded-full`} style={{ width: `${s.avance_pct}%` }} />
                  </div>
                </>
              )}
            </button>
          )
        })}
        {resumen && resumen.total_clientes_activos > 0 && (
          <p className="text-xs text-gray-400 text-center pb-1">
            {resumen.total_clientes_activos} clientes con órdenes activas
          </p>
        )}

        {/* Separador y conteo */}
        <div className="flex items-center gap-2 pt-1">
          <div className="flex-1 h-px bg-gray-200" />
          <p className="text-xs text-gray-400 whitespace-nowrap">
            {loadingOrd ? 'Cargando…' : `${total.toLocaleString()} órdenes`}
          </p>
          <div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* Lista de órdenes */}
        {loadingOrd && <div className="flex justify-center py-6"><div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>}
        {!loadingOrd && ordenes.length === 0 && <p className="text-center text-gray-400 py-8">Sin órdenes</p>}
        {ordenes.map(o => {
          const c = cfg(o.status)
          const isExp = expanded === o.id
          return (
            <div key={o.id} className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              <button className="w-full text-left p-4" onClick={() => setExpanded(isExp ? null : o.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${c.dot}`} />
                      <p className="text-xs font-mono text-gray-500">#{o.order_number}</p>
                      <span className={`text-xs px-1.5 py-0.5 rounded-full ${c.color}`}>{c.label}</span>
                    </div>
                    <p className="font-semibold text-gray-900 text-sm truncate">{o.customer_name ?? '—'}</p>
                    <p className="text-xs text-gray-500 truncate">{o.product_name}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-bold text-blue-700">{o.avance_pct}%</p>
                    <p className="text-xs text-gray-400">{Number(o.quantity_produced).toLocaleString()} / {Number(o.quantity_to_produce).toLocaleString()}</p>
                    {isExp ? <ChevronUp size={14} className="ml-auto mt-1 text-gray-400" /> : <ChevronDown size={14} className="ml-auto mt-1 text-gray-400" />}
                  </div>
                </div>
                <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div className={`h-full ${c.dot} rounded-full`} style={{ width: `${o.avance_pct}%` }} />
                </div>
              </button>
              {isExp && (
                <div className="border-t border-gray-100 px-4 pb-4 pt-3 space-y-1.5">
                  {o.sales_order_number && <Row label="Pedido venta" value={`#${o.sales_order_number}`} />}
                  {o.machine_name  && <Row label="Máquina"   value={o.machine_name}  />}
                  {o.area_name     && <Row label="Área"      value={o.area_name}     />}
                  {o.product_sku   && <Row label="SKU"       value={o.product_sku}   />}
                  {o.product_color && <Row label="Color"     value={o.product_color} />}
                  {o.delivery_date && <Row label="Entrega"   value={fmtDate(o.delivery_date)} />}
                  {o.actual_start_date && <Row label="Inicio producción" value={fmtDate(o.actual_start_date)} />}
                  {o.quantity_defective > 0 && <Row label="Defectuosas" value={String(o.quantity_defective)} danger />}
                  {o.notes && <p className="text-xs text-gray-500 mt-2 italic">{o.notes}</p>}
                </div>
              )}
            </div>
          )
        })}

        {total > 50 && !loadingOrd && (
          <div className="flex items-center justify-center gap-3 pt-2 pb-4">
            <button disabled={page === 1} onClick={() => setPage(p => p - 1)} className="px-3 py-1.5 text-xs border rounded-lg disabled:opacity-40">Anterior</button>
            <span className="text-xs text-gray-500">{page} / {Math.ceil(total / 50)}</span>
            <button disabled={ordenes.length < 50} onClick={() => setPage(p => p + 1)} className="px-3 py-1.5 text-xs border rounded-lg disabled:opacity-40">Siguiente</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 4 — Configuración de Asesores
// ══════════════════════════════════════════════════════════════════════════════

interface AsesorUser {
  id: number
  nombre: string
  username: string
  activo: boolean
}

interface AsesorFormData {
  nombre: string
  username: string
  password: string
}

function AsesorModal({
  modo,
  asesor,
  onClose,
  onSave,
}: {
  modo: 'crear' | 'editar' | 'clave'
  asesor?: AsesorUser
  onClose: () => void
  onSave: (data: Partial<AsesorFormData>) => Promise<void>
}) {
  const [form, setForm] = useState<AsesorFormData>({
    nombre:   asesor?.nombre   ?? '',
    username: asesor?.username ?? '',
    password: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (modo === 'crear' && (!form.nombre.trim() || !form.username.trim() || !form.password.trim())) {
      setError('Todos los campos son obligatorios')
      return
    }
    if (modo === 'clave' && !form.password.trim()) {
      setError('Ingresa la nueva contraseña')
      return
    }
    setSaving(true)
    try {
      if (modo === 'crear')  await onSave({ nombre: form.nombre, username: form.username, password: form.password })
      if (modo === 'editar') await onSave({ nombre: form.nombre, username: form.username })
      if (modo === 'clave')  await onSave({ password: form.password })
      onClose()
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  const titles = { crear: 'Nuevo Asesor', editar: 'Editar Asesor', clave: 'Cambiar Contraseña' }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-end justify-center" onClick={onClose}>
      <div className="bg-white rounded-t-2xl w-full max-w-lg p-5 pb-8" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <p className="font-bold text-gray-900">{titles[modo]}</p>
          <button onClick={onClose}><X size={18} className="text-gray-500" /></button>
        </div>
        {asesor && modo !== 'crear' && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 bg-blue-50 rounded-xl">
            <div className="w-8 h-8 bg-blue-700 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
              {asesor.nombre[0]}
            </div>
            <div>
              <p className="text-sm font-semibold text-blue-900">{asesor.nombre}</p>
              <p className="text-xs text-blue-600">@{asesor.username}</p>
            </div>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-2.5">
          {(modo === 'crear' || modo === 'editar') && (
            <>
              <div>
                <label className="block text-[11px] font-semibold text-gray-400 mb-1 uppercase tracking-wide">Nombre completo</label>
                <input
                  value={form.nombre}
                  onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
                  placeholder="Ej: Diana Cardona"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-400 mb-1 uppercase tracking-wide">Usuario (login)</label>
                <input
                  value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value.toLowerCase().replace(/\s/g, '') }))}
                  placeholder="Ej: diana"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </>
          )}
          {(modo === 'crear' || modo === 'clave') && (
            <div>
              <label className="block text-[11px] font-semibold text-gray-400 mb-1 uppercase tracking-wide">
                {modo === 'clave' ? 'Nueva contraseña' : 'Contraseña'}
              </label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="Mínimo 6 caracteres"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}
          {error && <p className="text-xs text-red-600 bg-red-50 px-3 py-1.5 rounded-lg">{error}</p>}
          <button
            type="submit"
            disabled={saving}
            className="w-full bg-blue-700 text-white text-sm font-semibold py-2.5 rounded-xl disabled:opacity-50"
          >
            {saving ? 'Guardando…' : titles[modo]}
          </button>
        </form>
      </div>
    </div>
  )
}

function TabConfig() {
  const [asesores, setAsesores] = useState<AsesorUser[]>([])
  const [loading, setLoading]   = useState(true)
  const [modal, setModal]       = useState<{ modo: 'crear' | 'editar' | 'clave'; asesor?: AsesorUser } | null>(null)
  const [toggling, setToggling] = useState<number | null>(null)

  function cargar() {
    setLoading(true)
    crmApi.listarAsesoresMgmt()
      .then(setAsesores)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { cargar() }, [])

  async function handleSave(data: Partial<AsesorFormData>) {
    if (modal?.modo === 'crear') {
      await crmApi.crearAsesor(data as any)
      toast.success('Asesor creado correctamente')
    } else if (modal?.asesor) {
      await crmApi.actualizarAsesor(modal.asesor.id, data)
      toast.success(modal.modo === 'clave' ? 'Contraseña actualizada' : 'Asesor actualizado')
    }
    cargar()
  }

  async function handleToggle(a: AsesorUser) {
    setToggling(a.id)
    try {
      await crmApi.toggleAsesor(a.id)
      toast.success(a.activo ? 'Asesor desactivado' : 'Asesor activado')
      cargar()
    } catch {
      toast.error('Error al cambiar estado')
    } finally {
      setToggling(null)
    }
  }

  return (
    <div className="p-2.5 space-y-2 pb-6">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-500 flex items-center gap-1">
          <Users size={11} /> ASESORES ({asesores.length})
        </p>
        <button
          onClick={() => setModal({ modo: 'crear' })}
          className="flex items-center gap-1 bg-blue-700 text-white text-xs font-semibold px-2.5 py-1.5 rounded-lg active:bg-blue-800"
        >
          <Plus size={12} /> Nuevo Asesor
        </button>
      </div>

      {loading && (
        <div className="flex justify-center py-10">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && asesores.length === 0 && (
        <div className="bg-white rounded-xl p-6 text-center text-gray-400 text-sm border border-gray-100">
          No hay asesores registrados
        </div>
      )}

      {asesores.map(a => (
        <div
          key={a.id}
          className={`bg-white rounded-lg shadow-sm border overflow-hidden ${
            a.activo ? 'border-gray-100' : 'border-gray-200 opacity-60'
          }`}
        >
          <div className={`px-3 py-2 flex items-center gap-2 ${a.activo ? 'bg-blue-800' : 'bg-gray-500'}`}>
            <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
              {a.nombre[0]}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white truncate leading-tight">{a.nombre}</p>
              <p className="text-xs text-blue-300 leading-tight">@{a.username}</p>
            </div>
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
              a.activo ? 'bg-green-500/25 text-green-100' : 'bg-red-500/25 text-red-100'
            }`}>
              {a.activo ? 'Activo' : 'Inactivo'}
            </span>
          </div>
          <div className="px-2 py-1.5 flex gap-1.5">
            <button
              onClick={() => setModal({ modo: 'editar', asesor: a })}
              className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 active:bg-gray-100"
            >
              <Pencil size={12} />
              <span className="text-xs font-medium">Editar</span>
            </button>
            <button
              onClick={() => setModal({ modo: 'clave', asesor: a })}
              className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 active:bg-gray-100"
            >
              <KeyRound size={12} />
              <span className="text-xs font-medium">Clave</span>
            </button>
            <button
              onClick={() => handleToggle(a)}
              disabled={toggling === a.id}
              className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg border text-xs font-medium disabled:opacity-50 ${
                a.activo
                  ? 'border-red-200 text-red-600 hover:bg-red-50'
                  : 'border-green-200 text-green-600 hover:bg-green-50'
              }`}
            >
              {a.activo ? <UserX size={12} /> : <UserCheck size={12} />}
              <span>{a.activo ? 'Desactivar' : 'Activar'}</span>
            </button>
          </div>
        </div>
      ))}

      {modal && (
        <AsesorModal
          modo={modal.modo}
          asesor={modal.asesor}
          onClose={() => setModal(null)}
          onSave={handleSave}
        />
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN GerenciaPage
// ══════════════════════════════════════════════════════════════════════════════

type Detalle = { type: 'kanban'; data: KanbanData } | { type: 'clientes'; data: ClientesData } | null

export default function GerenciaPage() {
  const [tab, setTab] = useState<'resumen' | 'clientes' | 'produccion'>('resumen')
  const [showConfig, setShowConfig] = useState(false)
  const [detalle, setDetalle] = useState<Detalle>(null)
  const [loadingDetalle, setLoadingDetalle] = useState(false)

  async function verKanban(id: number) {
    setLoadingDetalle(true)
    try { setDetalle({ type: 'kanban', data: await crmApi.gerenciaKanbanAsesor(id) }) } catch {}
    setLoadingDetalle(false)
  }
  async function verClientes(id: number) {
    setLoadingDetalle(true)
    try { setDetalle({ type: 'clientes', data: await crmApi.gerenciaClientesAsesor(id) }) } catch {}
    setLoadingDetalle(false)
  }

  if (detalle?.type === 'kanban')   return <KanbanAsesorView   data={detalle.data} onBack={() => setDetalle(null)} />
  if (detalle?.type === 'clientes') return <ClientesAsesorView data={detalle.data} onBack={() => setDetalle(null)} />

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tabs de navegación interna */}
      <div className="bg-white border-b flex gap-0 pt-3 pb-0 flex-shrink-0 overflow-x-auto scrollbar-none">
        <div className="flex flex-1">
          {([
            { id: 'resumen',    label: 'Asesores',    icon: Users     },
            { id: 'clientes',   label: 'Clientes ATH', icon: Building2 },
            { id: 'produccion', label: 'Producción',  icon: Package   },
          ] as const).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1 px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap ${
                tab === id ? 'border-blue-700 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowConfig(true)}
          className="flex-shrink-0 flex items-center justify-center w-10 h-10 text-gray-400 hover:text-blue-700 hover:bg-blue-50 rounded-lg mr-1 transition-colors"
          title="Configuración de asesores"
        >
          <Settings size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {tab === 'resumen'    && <TabResumen onKanban={verKanban} onClientes={verClientes} />}
        {tab === 'clientes'   && <TabClientes />}
        {tab === 'produccion' && <TabProduccion />}
      </div>

      {loadingDetalle && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="w-10 h-10 border-2 border-white border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {showConfig && (
        <div className="fixed inset-0 z-50 flex flex-col bg-gray-50">
          <div className="bg-blue-800 text-white px-3 py-2.5 flex items-center gap-2 flex-shrink-0">
            <button onClick={() => setShowConfig(false)} className="p-0.5">
              <ChevronRight size={18} className="rotate-180" />
            </button>
            <div>
              <p className="text-sm font-bold leading-tight">Configuración</p>
              <p className="text-[11px] text-blue-300">Gestión de asesores</p>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            <TabConfig />
          </div>
        </div>
      )}
    </div>
  )
}

