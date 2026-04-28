import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, menuApi, tablesApi } from '../../api'
import { User, MenuItem, MenuCategory, Table } from '../../types'
import toast from 'react-hot-toast'
import { Plus, X, Users, UtensilsCrossed, Table2 } from 'lucide-react'

type Tab = 'usuarios' | 'menu' | 'mesas'

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('usuarios')

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Administración</h1>
        <p className="text-gray-500 text-sm">Gestión de usuarios, menú y mesas</p>
      </div>
      <div className="flex gap-2 border-b border-gray-200">
        {([['usuarios', Users, 'Usuarios'], ['menu', UtensilsCrossed, 'Menú'], ['mesas', Table2, 'Mesas']] as const).map(([key, Icon, label]) => (
          <button key={key} onClick={() => setTab(key)} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${tab === key ? 'border-orange-500 text-orange-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            <Icon size={15} />{label}
          </button>
        ))}
      </div>
      {tab === 'usuarios' && <UsersTab />}
      {tab === 'menu' && <MenuTab />}
      {tab === 'mesas' && <MesasTab />}
    </div>
  )
}

function UsersTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ nombre: '', email: '', password: '', rol: 'mesero' })
  const { data: users = [] } = useQuery<User[]>({ queryKey: ['users'], queryFn: authApi.users })

  const createMutation = useMutation({
    mutationFn: (data: object) => authApi.createUser(data),
    onSuccess: () => { toast.success('Usuario creado'); qc.invalidateQueries({ queryKey: ['users'] }); setShowForm(false) },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, activo }: { id: number; activo: boolean }) => authApi.updateUser(id, { activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  const rolColors: Record<string, string> = { admin: 'bg-purple-100 text-purple-700', cajero: 'bg-blue-100 text-blue-700', mesero: 'bg-green-100 text-green-700', cocinero: 'bg-orange-100 text-orange-700' }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2"><Plus size={15} /> Nuevo usuario</button>
      </div>
      <div className="card overflow-hidden p-0">
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            <tr>{['Nombre', 'Email', 'Rol', 'Estado', 'Acciones'].map(h => (
              <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase px-4 py-3">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {(users as User[]).map((u: User) => (
              <tr key={u.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-sm">{u.nombre}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{u.email}</td>
                <td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full capitalize ${rolColors[u.rol]}`}>{u.rol}</span></td>
                <td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full ${u.activo ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>{u.activo ? 'Activo' : 'Inactivo'}</span></td>
                <td className="px-4 py-3">
                  <button onClick={() => toggleMutation.mutate({ id: u.id, activo: !u.activo })} className="text-xs text-orange-600 hover:text-orange-800">
                    {u.activo ? 'Desactivar' : 'Activar'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
            <h2 className="font-bold text-gray-900 mb-4">Nuevo Usuario</h2>
            <div className="space-y-3">
              {([['Nombre', 'nombre', 'text'], ['Email', 'email', 'email'], ['Contraseña', 'password', 'password']] as const).map(([label, key, type]) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <input type={type} className="input" value={(form as any)[key]} onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))} />
                </div>
              ))}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Rol</label>
                <select className="input" value={form.rol} onChange={e => setForm(p => ({ ...p, rol: e.target.value }))}>
                  {['admin', 'cajero', 'mesero', 'cocinero'].map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button onClick={() => createMutation.mutate(form)} disabled={createMutation.isPending} className="btn-primary flex-1">Crear</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MenuTab() {
  const qc = useQueryClient()
  const [showItemForm, setShowItemForm] = useState(false)
  const [showCatForm, setShowCatForm] = useState(false)
  const [itemForm, setItemForm] = useState({ nombre: '', descripcion: '', precio: 0, categoria_id: '' })
  const [catForm, setCatForm] = useState({ nombre: '', orden: 0 })

  const { data: items = [] } = useQuery<MenuItem[]>({ queryKey: ['menu-items-all'], queryFn: () => menuApi.items(false) })
  const { data: categories = [] } = useQuery<MenuCategory[]>({ queryKey: ['categories'], queryFn: menuApi.categories })

  const createItem = useMutation({
    mutationFn: (data: object) => menuApi.createItem(data),
    onSuccess: () => { toast.success('Ítem creado'); qc.invalidateQueries({ queryKey: ['menu-items-all'] }); setShowItemForm(false) },
  })
  const toggleItem = useMutation({
    mutationFn: ({ id, activo }: { id: number; activo: boolean }) => menuApi.updateItem(id, { activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['menu-items-all'] }),
  })
  const createCat = useMutation({
    mutationFn: (data: object) => menuApi.createCategory(data),
    onSuccess: () => { toast.success('Categoría creada'); qc.invalidateQueries({ queryKey: ['categories'] }); setShowCatForm(false) },
  })

  return (
    <div className="space-y-4">
      <div className="flex gap-2 justify-end">
        <button onClick={() => setShowCatForm(true)} className="btn-secondary text-sm">+ Categoría</button>
        <button onClick={() => setShowItemForm(true)} className="btn-primary text-sm flex items-center gap-1"><Plus size={14} /> Nuevo plato</button>
      </div>
      <div className="card overflow-hidden p-0">
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            <tr>{['Plato', 'Categoría', 'Precio', 'Estado', 'Acciones'].map(h => (
              <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase px-4 py-3">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {(items as MenuItem[]).map((item: MenuItem) => {
              const cat = (categories as MenuCategory[]).find((c: MenuCategory) => c.id === item.categoria_id)
              return (
                <tr key={item.id} className={`border-b last:border-0 hover:bg-gray-50 ${!item.activo ? 'opacity-50' : ''}`}>
                  <td className="px-4 py-3 font-medium text-sm">{item.nombre}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{cat?.nombre || '-'}</td>
                  <td className="px-4 py-3 text-sm font-semibold text-orange-600">${item.precio}</td>
                  <td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full ${item.activo ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>{item.activo ? 'Activo' : 'Inactivo'}</span></td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleItem.mutate({ id: item.id, activo: !item.activo })} className="text-xs text-orange-600 hover:text-orange-800">
                      {item.activo ? 'Desactivar' : 'Activar'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {showItemForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
            <h2 className="font-bold text-gray-900 mb-4">Nuevo Plato</h2>
            <div className="space-y-3">
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label><input type="text" className="input" value={itemForm.nombre} onChange={e => setItemForm(p => ({ ...p, nombre: e.target.value }))} /></div>
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Descripción</label><input type="text" className="input" value={itemForm.descripcion} onChange={e => setItemForm(p => ({ ...p, descripcion: e.target.value }))} /></div>
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Precio</label><input type="number" className="input" value={itemForm.precio} onChange={e => setItemForm(p => ({ ...p, precio: Number(e.target.value) }))} /></div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Categoría</label>
                <select className="input" value={itemForm.categoria_id} onChange={e => setItemForm(p => ({ ...p, categoria_id: e.target.value }))}>
                  <option value="">Sin categoría</option>
                  {(categories as MenuCategory[]).map((c: MenuCategory) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                </select>
              </div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowItemForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button onClick={() => createItem.mutate({ ...itemForm, categoria_id: itemForm.categoria_id ? Number(itemForm.categoria_id) : null })} disabled={createItem.isPending} className="btn-primary flex-1">Crear</button>
            </div>
          </div>
        </div>
      )}
      {showCatForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
            <h2 className="font-bold text-gray-900 mb-4">Nueva Categoría</h2>
            <div className="space-y-3">
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label><input type="text" className="input" value={catForm.nombre} onChange={e => setCatForm(p => ({ ...p, nombre: e.target.value }))} /></div>
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Orden</label><input type="number" className="input" value={catForm.orden} onChange={e => setCatForm(p => ({ ...p, orden: Number(e.target.value) }))} /></div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowCatForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button onClick={() => createCat.mutate(catForm)} disabled={createCat.isPending} className="btn-primary flex-1">Crear</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MesasTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ numero: 1, capacidad: 4, zona: 'salon' })
  const { data: tables = [] } = useQuery<Table[]>({ queryKey: ['tables'], queryFn: tablesApi.list })

  const createMutation = useMutation({
    mutationFn: (data: object) => tablesApi.create(data),
    onSuccess: () => { toast.success('Mesa creada'); qc.invalidateQueries({ queryKey: ['tables'] }); setShowForm(false) },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Error'),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => tablesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tables'] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2"><Plus size={15} /> Nueva mesa</button>
      </div>
      <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 gap-3">
        {(tables as Table[]).map((t: Table) => (
          <div key={t.id} className="card text-center p-3 relative group">
            <div className="text-xl font-bold text-gray-800">{t.numero}</div>
            <div className="text-xs text-gray-400">{t.capacidad} pers.</div>
            <div className="text-xs text-gray-400">{t.zona}</div>
            <button onClick={() => deleteMutation.mutate(t.id)} className="absolute top-1 right-1 text-gray-200 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"><X size={12} /></button>
          </div>
        ))}
      </div>
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl p-6">
            <h2 className="font-bold text-gray-900 mb-4">Nueva Mesa</h2>
            <div className="space-y-3">
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Número</label><input type="number" className="input" value={form.numero} onChange={e => setForm(p => ({ ...p, numero: Number(e.target.value) }))} /></div>
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Capacidad</label><input type="number" className="input" value={form.capacidad} onChange={e => setForm(p => ({ ...p, capacidad: Number(e.target.value) }))} /></div>
              <div><label className="block text-sm font-medium text-gray-700 mb-1">Zona</label><input type="text" className="input" value={form.zona} onChange={e => setForm(p => ({ ...p, zona: e.target.value }))} /></div>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button onClick={() => createMutation.mutate(form)} disabled={createMutation.isPending} className="btn-primary flex-1">Crear</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
