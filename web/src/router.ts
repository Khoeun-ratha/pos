import { createRouter, createWebHistory } from 'vue-router'

import type { Permission } from '@/api/types'
import { t } from '@/lib/i18n'
import { useAuth } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** the role needs this permission (or one of these) */
    perm?: Permission | Permission[]
    admin?: boolean
    public?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: () => (useAuth().can('reports') ? '/dashboard' : '/sell') },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: 'Dashboard', perm: 'reports' } },
        { path: 'sell', name: 'sell', component: () => import('@/views/SellView.vue'), meta: { title: 'POS' } },
        { path: 'sales', name: 'sales', component: () => import('@/views/SalesView.vue'), meta: { title: 'Sales' } },
        { path: 'shift', name: 'shift', component: () => import('@/views/ShiftView.vue'), meta: { title: 'Shift' } },
        { path: 'reports', name: 'reports', component: () => import('@/views/ReportsView.vue'), meta: { title: 'Reports', perm: 'reports' } },
        { path: 'products', name: 'products', component: () => import('@/views/ProductsView.vue'), meta: { title: 'Products', perm: 'products' } },
        { path: 'labels', name: 'labels', component: () => import('@/views/LabelsView.vue'), meta: { title: 'Barcode & QR labels', perm: ['products', 'inventory'] } },
        { path: 'inventory', name: 'inventory', component: () => import('@/views/InventoryView.vue'), meta: { title: 'Stock levels', perm: 'inventory' } },
        { path: 'inventory/low', name: 'low-stock', component: () => import('@/views/InventoryView.vue'), meta: { title: 'Low stock', perm: 'inventory' } },
        { path: 'inventory/movements', name: 'movements', component: () => import('@/views/InventoryView.vue'), meta: { title: 'Stock movements', perm: 'inventory' } },
        { path: 'inventory/transfers', name: 'transfers', component: () => import('@/views/TransfersView.vue'), meta: { title: 'Stock transfers', perm: 'inventory' } },
        { path: 'inventory/locations', name: 'locations', component: () => import('@/views/LocationsView.vue'), meta: { title: 'Branches & warehouses', perm: 'inventory' } },
        { path: 'suppliers', name: 'suppliers', component: () => import('@/views/SuppliersView.vue'), meta: { title: 'Suppliers', perm: 'suppliers' } },
        { path: 'customers', name: 'customers', component: () => import('@/views/CustomersView.vue'), meta: { title: 'Customers' } },
        { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue'), meta: { title: 'Store settings' } },
        { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue'), meta: { title: 'Users', admin: true } },
        { path: 'permissions', name: 'permissions', component: () => import('@/views/PermissionsView.vue'), meta: { title: 'Roles & permissions', admin: true } },
        { path: 'activity', name: 'activity', component: () => import('@/views/ActivityView.vue'), meta: { title: 'Activity log', admin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

/** Permissions are fetched once per page load, so a change the admin made is used before the first page opens. */
let permissionsChecked = false

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (to.meta.public) return auth.loggedIn && to.name === 'login' ? '/' : true
  if (!auth.loggedIn) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (!permissionsChecked) {
    permissionsChecked = true
    await auth.refreshPermissions().catch(() => {}) // offline: keep the saved ones
  }
  if (to.meta.admin && !auth.isAdmin) return '/sell'
  const perms = to.meta.perm === undefined ? [] : Array.isArray(to.meta.perm) ? to.meta.perm : [to.meta.perm]
  if (perms.length && !perms.some((p) => auth.can(p))) return '/sell'
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title && to.meta.title !== 'POS' ? `${t(to.meta.title)} · POS` : 'POS'
})
