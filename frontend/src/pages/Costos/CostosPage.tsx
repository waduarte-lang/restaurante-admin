import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi, expensesApi } from '../../api'
import { Expense } from '../../types'
import toast from 'react-hot-toast'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { Plus, X } from 'lucide-react'

const COLORS = ['#f97316', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899']

export default function CostosPage() {
  const qc = useQueryClient()
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)
  const [showExpenseForm, setShowExpenseForm] = useState(false)
  const [expForm, setExpForm] = useState({ concepto: '', monto: 0, categoria: 'general', fecha: today.toISOString().split('T')[0] })

  const { data: financial } = useQuery({ queryKey: ['financial', year, month], queryFn: () => reportsApi.financial(year, month) })
  const { data: costs = [] } = useQuery({ queryKey: ['costs'], queryFn: reportsApi.costs })
  const { data: expenses = [] } = useQuery<Expense[]>({ queryKey: ['expenses', year, month], queryFn: () => expensesApi.list({ fecha_inicio: `${year}-${String(month).padStart(2,'0')}-01` }) })

  const createExpense = useMutation({
    mutationFn: (data: object) => expensesApi.create(data),
    onSuccess: () => { toast.success('Gasto registrado'); qc.invalidateQueries({ queryKey: ['expenses'] }); qc.invalidateQueries({ queryKey: ['financial'] }); setShowExpenseForm(false) },
    onError: () => toast.error('Error al registrar gasto'),
  })

  const deleteExpense = useMutation({
    mutationFn: (id: number) => expensesApi.delete(id),
    onSuccess: () => { toast.success('Gasto eliminado'); qc.invalidateQueries({ queryKey: ['expenses'] }); qc.invalidateQueries({ queryKey: ['financial'] }) },
  })

  const months = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

  const finData = financial ? [
    { name: 'Ingresos', value: financial.ingresos },
    { name: 'Costo ventas', value: financial.costo_ventas },
    { name: 'Gastos', value: financial.gastos_operativos },
    { name: 'Utilidad neta', value: financial.utilidad_neta },
  ] : []

  const expByCategory = (expenses as Expense[]).reduce((acc: any, e) => {
    acc[e.categoria] = (acc[e.categoria] || 0) + e.monto
    return acc
  }, {})
  const pieData = Object.entries(expByCategory).map(([name, value]) => ({ name, value }))

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Costos y Finanzas</h1>
          <p className="text-gray-500 text-sm">Estados financieros y análisis de rentabilidad</p>
        </div>
        <div className="flex items-center gap-3">
          <select className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" value={month} onChange={e => setMonth(Number(e.target.value))}>
            {months.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <select className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" value={year} onChange={e => setYear(Number(e.target.value))}>
            {[2024, 2025, 2026].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {financial && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            {[
              { label: 'Ingresos', value: financial.ingresos, color: 'text-green-600' },
              { label: 'Costo de ventas', value: financial.costo_ventas, color: 'text-red-500' },
              { label: 'Utilidad bruta', value: financial.utilidad_bruta, color: 'text-blue-600' },
              { label: 'Gastos operativos', value: financial.gastos_operativos, color: 'text-orange-500' },
              { label: 'Utilidad neta', value: financial.utilidad_neta, color: financial.utilidad_neta >= 0 ? 'text-green-600' : 'text-red-600' },
            ].map(({ label, value, color }) => (
              <div key={label} className="card">
                <p className="text-xs text-gray-500">{label}</p>
                <p className={`text-xl font-bold mt-1 ${color}`}>${value.toLocaleString()}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="card">
              <h2 className="font-semibold text-gray-800 mb-4">Estado de resultados</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={finData}>
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: any) => [`$${Number(v).toLocaleString()}`, '']} />
                  <Bar dataKey="value" fill="#f97316" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-3 flex gap-4 text-sm">
                <span>Margen bruto: <b>{financial.margen_bruto_pct}%</b></span>
                <span>Margen neto: <b>{financial.margen_neto_pct}%</b></span>
              </div>
            </div>

            {pieData.length > 0 && (
              <div className="card">
                <h2 className="font-semibold text-gray-800 mb-4">Gastos por categoría</h2>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                      {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v: any) => [`$${v}`, '']} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800">Gastos operativos</h2>
            <button onClick={() => setShowExpenseForm(true)} className="btn-primary text-sm py-1.5 flex items-center gap-1">
              <Plus size={14} /> Agregar
            </button>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {(expenses as Expense[]).length === 0 && <p className="text-gray-400 text-sm">Sin gastos registrados</p>}
            {(expenses as Expense[]).map((e: Expense) => (
              <div key={e.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <div>
                  <span className="text-sm font-medium">{e.concepto}</span>
                  <span className="text-xs text-gray-400 ml-2 capitalize">{e.categoria}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-red-500">-${e.monto}</span>
                  <button onClick={() => deleteExpense.mutate(e.id)} className="text-gray-300 hover:text-red-400"><X size={14} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2 className="font-semibold text-gray-800 mb-4">Rentabilidad por plato</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {(costs as any[]).map((c: any) => (
              <div key={c.id} className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0">
                <div className="flex-1">
                  <span className="text-sm font-medium">{c.nombre}</span>
                  <div className="text-xs text-gray-400">Precio: ${c.precio} · Costo: ${c.costo}</div>
                </div>
                <span className={`text-sm font-bold ${c.margen_pct > 30 ? 'text-green-600' : c.margen_pct > 10 ? 'text-yellow-600' : 'text-red-500'}`}>
                  {c.margen_pct}%
                </span>
              </div>
            ))}
            {(costs as any[]).length === 0 && <p className="text-gray-400 text-sm">No hay platos con recetas registradas</p>}
          </div>
        </div>
      </div>

      {showExpenseForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
            <h2 className="font-bold text-gray-900 mb-4">Nuevo Gasto</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Concepto</label>
                <input type="text" className="input" value={expForm.concepto} onChange={e => setExpForm(p => ({ ...p, concepto: e.target.value }))} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Monto</label>
                <input type="number" className="input" value={expForm.monto} onChange={e => setExpForm(p => ({ ...p, monto: Number(e.target.value) }))} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Categoría</label>
                <select className="input" value={expForm.categoria} onChange={e => setExpForm(p => ({ ...p, categoria: e.target.value }))}>
                  {['personal', 'servicios', 'insumos', 'mantenimiento', 'general'].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Fecha</label>
                <input type="date" className="input" value={expForm.fecha} onChange={e => setExpForm(p => ({ ...p, fecha: e.target.value }))} />
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowExpenseForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button onClick={() => createExpense.mutate(expForm)} disabled={createExpense.isPending} className="btn-primary flex-1">Guardar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
