import api from './client'

// Auth
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }).then(r => r.data),
  me: () => api.get('/auth/me').then(r => r.data),
  users: () => api.get('/auth/users').then(r => r.data),
  createUser: (data: object) => api.post('/auth/users', data).then(r => r.data),
  updateUser: (id: number, data: object) => api.put(`/auth/users/${id}`, data).then(r => r.data),
  deleteUser: (id: number) => api.delete(`/auth/users/${id}`).then(r => r.data),
}

// Tables
export const tablesApi = {
  list: () => api.get('/tables').then(r => r.data),
  create: (data: object) => api.post('/tables', data).then(r => r.data),
  update: (id: number, data: object) => api.put(`/tables/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/tables/${id}`).then(r => r.data),
}

// Menu
export const menuApi = {
  categories: () => api.get('/menu/categories').then(r => r.data),
  createCategory: (data: object) => api.post('/menu/categories', data).then(r => r.data),
  deleteCategory: (id: number) => api.delete(`/menu/categories/${id}`).then(r => r.data),
  items: (activo = true) => api.get('/menu/items', { params: { activo } }).then(r => r.data),
  createItem: (data: object) => api.post('/menu/items', data).then(r => r.data),
  updateItem: (id: number, data: object) => api.put(`/menu/items/${id}`, data).then(r => r.data),
  deleteItem: (id: number) => api.delete(`/menu/items/${id}`).then(r => r.data),
}

// Orders
export const ordersApi = {
  list: (estado?: string) => api.get('/orders', { params: estado ? { estado } : {} }).then(r => r.data),
  get: (id: number) => api.get(`/orders/${id}`).then(r => r.data),
  create: (data: object) => api.post('/orders', data).then(r => r.data),
  update: (id: number, data: object) => api.put(`/orders/${id}`, data).then(r => r.data),
  addItem: (id: number, item_id: number, cantidad: number, nota?: string) =>
    api.post(`/orders/${id}/items`, null, { params: { item_id, cantidad, nota } }).then(r => r.data),
}

// Inventory
export const inventoryApi = {
  ingredients: () => api.get('/inventory/ingredients').then(r => r.data),
  createIngredient: (data: object) => api.post('/inventory/ingredients', data).then(r => r.data),
  updateIngredient: (id: number, data: object) => api.put(`/inventory/ingredients/${id}`, data).then(r => r.data),
  movements: (ingredient_id?: number) => api.get('/inventory/movements', { params: ingredient_id ? { ingredient_id } : {} }).then(r => r.data),
  addMovement: (data: object) => api.post('/inventory/movements', data).then(r => r.data),
  recipes: (item_id: number) => api.get(`/inventory/recipes/${item_id}`).then(r => r.data),
  createRecipe: (data: object) => api.post('/inventory/recipes', data).then(r => r.data),
  deleteRecipe: (id: number) => api.delete(`/inventory/recipes/${id}`).then(r => r.data),
}

// Payments
export const paymentsApi = {
  create: (data: object) => api.post('/payments', data).then(r => r.data),
  cashRegisters: () => api.get('/payments/cash-registers').then(r => r.data),
  activeCashRegister: () => api.get('/payments/cash-registers/active').then(r => r.data),
  openRegister: (data: object) => api.post('/payments/cash-registers/open', data).then(r => r.data),
  closeRegister: (id: number, data: object) => api.post(`/payments/cash-registers/${id}/close`, data).then(r => r.data),
}

// Reports
export const reportsApi = {
  sales: (fecha_inicio?: string, fecha_fin?: string) =>
    api.get('/reports/sales', { params: { fecha_inicio, fecha_fin } }).then(r => r.data),
  topItems: (fecha_inicio?: string, fecha_fin?: string) =>
    api.get('/reports/top-items', { params: { fecha_inicio, fecha_fin } }).then(r => r.data),
  financial: (year?: number, month?: number) =>
    api.get('/reports/financial', { params: { year, month } }).then(r => r.data),
  costs: () => api.get('/reports/costs').then(r => r.data),
}

// Expenses
export const expensesApi = {
  list: (params?: object) => api.get('/expenses', { params }).then(r => r.data),
  create: (data: object) => api.post('/expenses', data).then(r => r.data),
  update: (id: number, data: object) => api.put(`/expenses/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/expenses/${id}`).then(r => r.data),
}
