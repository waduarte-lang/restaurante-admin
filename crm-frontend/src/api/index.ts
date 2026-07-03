import api from './client'

export const authApi = {
  login: (username: string, password: string) =>
    api.post('/auth/login', { username, password }).then(r => r.data),
  me: () => api.get('/auth/me').then(r => r.data),
}

export const crmApi = {
  // Clientes
  clientes: (q?: string, asesor_id?: number) =>
    api.get('/crm/clientes/', { params: { ...(q ? { q } : {}), ...(asesor_id ? { asesor_id } : {}) } }).then(r => r.data),
  asesores: () =>
    api.get('/crm/gerencia/asesores').then(r => r.data),
  cliente: (id: number) =>
    api.get(`/crm/clientes/${id}`).then(r => r.data),
  createCliente: (data: object) =>
    api.post('/crm/clientes/', data).then(r => r.data),
  updateCliente: (id: number, data: object) =>
    api.put(`/crm/clientes/${id}`, data).then(r => r.data),

  // Pedidos
  pedidos: (params?: { cliente_id?: number; estado?: string; q?: string; page?: number; per_page?: number }) =>
    api.get('/crm/pedidos/', { params }).then(r => r.data),
  pedidosPDF: async (params?: { q?: string; cliente_id?: number; estado?: string }) => {
    const r = await api.get('/crm/pedidos/pdf', { params, responseType: 'blob' })
    return r.data as Blob
  },
  pedido: (id: string) =>
    api.get(`/crm/pedidos/${id}`).then(r => r.data),

  // Cuentas (facturas y cartera)
  facturas: (clienteId: number) =>
    api.get(`/crm/cuentas/cliente/${clienteId}/facturas`).then(r => r.data),
  cartera: (clienteId: number) =>
    api.get(`/crm/cuentas/cliente/${clienteId}/cartera`).then(r => r.data),
  pagos: (clienteId: number) =>
    api.get(`/crm/cuentas/cliente/${clienteId}/pagos`).then(r => r.data),
  resumenCuenta: (clienteId: number) =>
    api.get(`/crm/cuentas/cliente/${clienteId}/resumen`).then(r => r.data),

  // Visitas
  visitas: (params?: { cliente_id?: number }) =>
    api.get('/crm/visitas/', { params }).then(r => r.data),
  createVisita: (data: object) =>
    api.post('/crm/visitas/', data).then(r => r.data),
  updateVisita: (id: number, data: object) =>
    api.put(`/crm/visitas/${id}`, data).then(r => r.data),
  deleteVisita: (id: number) =>
    api.delete(`/crm/visitas/${id}`).then(r => r.data),

  // Calendario
  eventos: (params?: { year?: number; month?: number }) =>
    api.get('/crm/calendario/', { params }).then(r => r.data),
  createEvento: (data: object) =>
    api.post('/crm/calendario/', data).then(r => r.data),
  updateEvento: (id: number, data: object) =>
    api.put(`/crm/calendario/${id}`, data).then(r => r.data),
  deleteEvento: (id: number) =>
    api.delete(`/crm/calendario/${id}`).then(r => r.data),

  // Gerencia
  gerenciaResumen: () =>
    api.get('/crm/gerencia/resumen').then(r => r.data),
  gerenciaAsesores: () =>
    api.get('/crm/gerencia/asesores').then(r => r.data),
  gerenciaClientesDatha: (params?: { q?: string; asesor_id?: number; sin_asignar?: boolean; page?: number; per_page?: number }) =>
    api.get('/crm/gerencia/clientes-datha', { params }).then(r => r.data),
  gerenciaAsignarAsesor: (data: object) =>
    api.post('/crm/gerencia/cliente-datha/asignar', data).then(r => r.data),
  gerenciaOrdenesResumen: () =>
    api.get('/crm/gerencia/ordenes-resumen').then(r => r.data),
  gerenciaOrdenes: (params?: { estado?: string; q?: string; page?: number; per_page?: number }) =>
    api.get('/crm/gerencia/ordenes', { params }).then(r => r.data),
  gerenciaKanbanAsesor: (asesorId: number) =>
    api.get(`/crm/gerencia/asesor/${asesorId}/kanban`).then(r => r.data),
  gerenciaClientesAsesor: (asesorId: number) =>
    api.get(`/crm/gerencia/asesor/${asesorId}/clientes`).then(r => r.data),

  // Gestión de asesores (gerente/admin)
  listarAsesoresMgmt: () =>
    api.get('/crm/gerencia/usuarios').then(r => r.data),
  crearAsesor: (data: { nombre: string; username: string; password: string }) =>
    api.post('/crm/gerencia/usuarios', data).then(r => r.data),
  actualizarAsesor: (id: number, data: { nombre?: string; username?: string; password?: string }) =>
    api.put(`/crm/gerencia/usuarios/${id}`, data).then(r => r.data),
  toggleAsesor: (id: number) =>
    api.patch(`/crm/gerencia/usuarios/${id}/toggle`).then(r => r.data),

  // Cartera ATH (cartera_facturas)
  carteraByNit: (nit: string) =>
    api.get('/crm/cartera/facturas', { params: { nit, per_page: 500 } }).then(r => r.data),

  carteraResumenVendedores: () =>
    api.get('/crm/cartera/resumen-vendedores').then(r => r.data as Array<{
      vendedor: string; total: number; num_facturas: number;
      vigente: number; d30: number; d60: number; d90: number; d90_mas: number
    }>),

  carteraResumen: (vendedor?: string) =>
    api.get('/crm/cartera/resumen', { params: vendedor ? { vendedor } : {} }).then(r => r.data),
  carteraFacturas: (params?: { q?: string; vendedor?: string; bucket?: string; page?: number; per_page?: number }) =>
    api.get('/crm/cartera/facturas', { params }).then(r => r.data),
  carteraPdf: async (params?: { vendedor?: string; nit?: string; q?: string; bucket?: string }) => {
    const r = await api.get('/crm/cartera/pdf', { params, responseType: 'blob' })
    return r.data as Blob
  },

  // Tareas (Planificador + Kanban)
  tareas: (params?: { fecha_desde?: string; fecha_hasta?: string; etapa?: string; cliente_id?: number }) =>
    api.get('/crm/tareas/', { params }).then(r => r.data),
  kanban: () =>
    api.get('/crm/tareas/kanban').then(r => r.data),
  createTarea: (data: object) =>
    api.post('/crm/tareas/', data).then(r => r.data),
  updateTarea: (id: number, data: object) =>
    api.put(`/crm/tareas/${id}`, data).then(r => r.data),
  deleteTarea: (id: number) =>
    api.delete(`/crm/tareas/${id}`).then(r => r.data),
}

// Lista de Precios y Cotizaciones ATH
export const preciosApi = {
  uploadCSV: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/crm/precios/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  categorias: () =>
    api.get('/crm/precios/categorias').then(r => r.data),
  buscarProductos: (q = '', categoria = '', skip = 0, limit = 60) =>
    api.get('/crm/precios/productos', { params: { q, categoria, skip, limit } }).then(r => r.data),
  crearCotizacion: (data: object) =>
    api.post('/crm/cotizaciones', data).then(r => r.data),
  listarCotizaciones: (skip = 0, limit = 50) =>
    api.get('/crm/cotizaciones', { params: { skip, limit } }).then(r => r.data),
  descargarPDF: (id: number) =>
    api.get(`/crm/cotizaciones/${id}/pdf`, { responseType: 'blob' }).then(r => r.data),
}
