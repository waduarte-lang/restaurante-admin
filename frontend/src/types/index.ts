export type Rol = 'admin' | 'cajero' | 'mesero' | 'cocinero'

export interface User {
  id: number
  nombre: string
  email: string
  rol: Rol
  activo: boolean
}

export interface Table {
  id: number
  numero: number
  capacidad: number
  estado: 'libre' | 'ocupada' | 'esperando_pago'
  zona: string
}

export interface MenuCategory {
  id: number
  nombre: string
  orden: number
}

export interface MenuItem {
  id: number
  nombre: string
  descripcion?: string
  precio: number
  categoria_id?: number
  activo: boolean
}

export interface OrderItem {
  id: number
  item_id: number
  cantidad: number
  precio_unitario: number
  nota?: string
  estado: string
  item_nombre?: string
}

export interface Order {
  id: number
  mesa_id: number
  mesero_id?: number
  estado: 'abierto' | 'en_cocina' | 'listo' | 'pagado' | 'cancelado'
  total: number
  observaciones?: string
  created_at: string
  items: OrderItem[]
}

export interface Ingredient {
  id: number
  nombre: string
  unidad: string
  stock_actual: number
  stock_minimo: number
  costo_unitario: number
  proveedor?: string
  bajo_stock: boolean
}

export interface StockMovement {
  id: number
  ingredient_id: number
  tipo: 'entrada' | 'salida'
  cantidad: number
  motivo?: string
  created_at: string
}

export interface CashRegister {
  id: number
  cajero_id: number
  fondo_inicial: number
  total_final?: number
  estado: 'abierta' | 'cerrada'
  apertura: string
  cierre?: string
}

export interface Payment {
  id: number
  order_id: number
  monto: number
  metodo: 'efectivo' | 'tarjeta' | 'transferencia'
  cajero_id?: number
  created_at: string
}

export interface Expense {
  id: number
  concepto: string
  monto: number
  categoria: string
  fecha: string
  created_at: string
}
