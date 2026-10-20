import { createRouter, createWebHistory } from 'vue-router'

import { t } from '@/lib/i18n'
import { useAuth } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    manager?: boolean
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
        { path: '', redirect: () => (useAuth().isManager ? '/dashboard' : '/sell') },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: 'Dashboard', manager: true } },
        { path: 'sell', name: 'sell', component: () => import('@/views/SellView.vue'), meta: { title: 'POS' } },
        { path: 'sales', name: 'sales', component: () => import('@/views/SalesView.vue'), meta: { title: 'Sales' } },
        { path: 'shift', name: 'shift', component: () => import('@/views/ShiftView.vue'), meta: { title: 'Shift' } },
        { path: 'reports', name: 'reports', component: () => import('@/views/ReportsView.vue'), meta: { title: 'Reports', manager: true } },
        { path: 'products', name: 'products', component: () => import('@/views/ProductsView.vue'), meta: { title: 'Products', manager: true } },
        { path: 'suppliers', name: 'suppliers', component: () => import('@/views/SuppliersView.vue'), meta: { title: 'Suppliers', manager: true } },
        { path: 'customers', name: 'customers', component: () => import('@/views/CustomersView.vue'), meta: { title: 'Customers' } },
        { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue'), meta: { title: 'Store settings' } },
        { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue'), meta: { title: 'Users', admin: true } },
        { path: 'activity', name: 'activity', component: () => import('@/views/ActivityView.vue'), meta: { title: 'Activity log', admin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuth()
  if (to.meta.public) return auth.loggedIn && to.name === 'login' ? '/' : true
  if (!auth.loggedIn) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (to.meta.admin && !auth.isAdmin) return '/sell'
  if (to.meta.manager && !auth.isManager) return '/sell'
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title && to.meta.title !== 'POS' ? `${t(to.meta.title)} · POS` : 'POS'
})
