import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { inventoryApi } from '../../api'
import { Ingredient } from '../../types'
import toast from 'react-hot-toast'
import { AlertTriangle, Plus, ArrowDown, ArrowUp } from 'lucide-react'

export default function InventarioPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [movModal, setMovModal] = useState<Ingredient | null>(null)
  const [form, setForm] = useState({ nombre: '', unidad: 'kg', stock_actual: 0, stock_minimo: 0, costo_unitario: 0, proveedor: '' })

  const { data: ingredients = [] } = useQuery<Ingredient[]>({ queryKey: ['ingredients'], queryFn: inventoryApi.ingredients })

  const createMutation = useMutation({
    mutationFn: (data: object) => inventoryApi.createIngredient(data),
    onSuccess: () => { toast.success('Ingrediente creado'); qc.invalidateQueries({ queryKey: ['ingredients'] }); setShowForm(false) },
    onError: () => toast.error('Error al crear ingrediente'),
  })

  const lowStock = ingredients.filter((i: Ingredient) => i.bajo_stock)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Inventario</h1>
          <p className="text-gray-500 text-sm">Control de insumos y materias primas</p>
        </div>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2">
          <Plus size={16} /> Nuevo insumo
        </button>
      </div>

      {lowStock.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="text-red-500 mt-0.5" size={18} />
          <div>
            <p className="font-medium text-red-700">Alerta de stock bajo</p>
            <p className="text-sm text-red-600">{lowStock.map((i: Ingredient) => i.nombre).join(', ')}</p>
          </div>
        </div>
      )}

      <div className="card overflow-hidden p-0">
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            <tr>
              {['Insumo', 'Unidad', 'Stock actual', 'Stock mínimo', 'Costo unitario', 'Proveedor', 'Acciones'].map(h => (
                <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wide px-4 py-3">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ingredients.map((ing: Ingredient) => (
              <tr key={ing.id} className={`border-b last:border-0 hover:bg-gray-50 ${ing.bajo_stock ? 'bg-red-50' : ''}`}>
                <td className="px-4 py-3 font-medium text-sm text-gray-800">{ing.nombre}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{ing.unidad}</td>
                <td className="px-4 py-3">
                  <span className={`text-sm font-semibold ${ing.bajo_stock ? 'text-red-600' : 'text-gray-800'}`}>
                    {ing.stock_actual} {ing.bajo_stock && '⚠'}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">{ing.stock_minimo}</td>
                <td className="px-4 py-3 text-sm text-gray-500">${ing.costo_unitario}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{ing.proveedor || '-'}</td>
                <td className="px-4 py-3">
                  <button onClick={() => setMovModal(ing)} className="text-xs text-orange-600 hover:text-orange-800 font-medium">
                    Movimiento
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl p-6">
            <h2 className="font-bold text-gray-900 mb-4">Nuevo Insumo</h2>
            <div className="space-y-3">
              {[
                { label: 'Nombre', key: 'nombre', type: 'text' },
                { label: 'Unidad', key: 'unidad', type: 'text' },
                { label: 'Stock inicial', key: 'stock_actual', type: 'number' },
                { label: 'Stock mínimo', key: 'stock_minimo', type: 'number' },
                { label: 'Costo unitario', key: 'costo_unitario', type: 'number' },
                { label: 'Proveedor', key: 'proveedor', type: 'text' },
              ].map(({ label, key, type }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <input type={type} className="input" value={(form as any)[key]}
                    onChange={e => setForm(p => ({ ...p, [key]: type === 'number' ? Number(e.target.value) : e.target.value }))} />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button onClick={() => createMutation.mutate(form)} disabled={createMutation.isPending} className="btn-primary flex-1">Guardar</button>
            </div>
          </div>
        </div>
      )}

      {movModal && (
        <MovementModal
          ingredient={movModal}
          onClose={() => setMovModal(null)}
          onSuccess={() => { qc.invalidateQueries({ queryKey: ['ingredients'] }); setMovModal(null) }}
        />
      )}
    </div>
  )
}

function MovementModal({ ingredient, onClose, onSuccess }: { ingredient: Ingredient; onClose: () => void; onSuccess: () => void }) {
  const [tipo, setTipo] = useState<'entrada' | 'salida'>('entrada')
  const [cantidad, setCantidad] = useState(1)
  const [motivo, setMotivo] = useState('')

  const mutation = useMutation({
    mutationFn: (data: object) => inventoryApi.addMovement(data),
    onSuccess: () => { toast.success('Movimiento registrado'); onSuccess() },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error'),
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
        <h2 className="font-bold text-gray-900 mb-1">Movimiento de Stock</h2>
        <p className="text-sm text-gray-500 mb-4">{ingredient.nombre} — Stock: {ingredient.stock_actual} {ingredient.unidad}</p>
        <div className="flex gap-3 mb-4">
          {(['entrada', 'salida'] as const).map(t => (
            <button key={t} onClick={() => setTipo(t)} className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg border-2 text-sm font-medium transition-colors ${tipo === t ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-600'}`}>
              {t === 'entrada' ? <ArrowDown size={15} /> : <ArrowUp size={15} />}
              {t === 'entrada' ? 'Entrada' : 'Salida'}
            </button>
          ))}
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Cantidad</label>
            <input type="number" min={0.01} step={0.01} className="input" value={cantidad} onChange={e => setCantidad(Number(e.target.value))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Motivo</label>
            <input type="text" className="input" value={motivo} onChange={e => setMotivo(e.target.value)} placeholder="Compra, merma, etc." />
          </div>
        </div>
        <div className="flex gap-3 mt-5">
          <button onClick={onClose} className="btn-secondary flex-1">Cancelar</button>
          <button onClick={() => mutation.mutate({ ingredient_id: ingredient.id, tipo, cantidad, motivo })} disabled={mutation.isPending} className="btn-primary flex-1">Registrar</button>
        </div>
      </div>
    </div>
  )
}
