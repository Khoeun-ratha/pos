<script setup lang="ts">
import {
  ChartColumn,
  ChevronsLeft,
  ChevronsRight,
  Clock,
  History,
  LayoutDashboard,
  LockKeyhole,
  LockKeyholeOpen,
  LogOut,
  Menu,
  Package,
  ReceiptText,
  ShoppingCart,
  Store,
  Truck,
  UserCog,
  Users,
} from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { lang, setLang, t } from '@/lib/i18n'
import { khr } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useShift } from '@/stores/shift'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const shift = useShift()
const ui = useUi()
const route = useRoute()
const router = useRouter()

const collapsed = ref(localStorage.getItem('pos.menu') === 'collapsed')
const drawerOpen = ref(false)
watch(collapsed, (v) => localStorage.setItem('pos.menu', v ? 'collapsed' : 'open'))
watch(() => route.fullPath, () => (drawerOpen.value = false))

const items = computed(() =>
  [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, manager: true },
    { to: '/sell', label: 'POS', icon: ShoppingCart },
    { to: '/sales', label: 'Sales', icon: ReceiptText },
    { to: '/shift', label: 'Shift', icon: Clock },
    { to: '/reports', label: 'Reports', icon: ChartColumn, manager: true },
    { to: '/products', label: 'Products', icon: Package, manager: true },
    { to: '/suppliers', label: 'Suppliers', icon: Truck, manager: true },
    { to: '/customers', label: 'Customers', icon: Users },
    { to: '/settings', label: 'Store settings', icon: Store },
    { to: '/users', label: 'Users', icon: UserCog, admin: true },
    { to: '/activity', label: 'Activity log', icon: History, admin: true },
  ].filter((i) => (!i.manager || auth.isManager) && (!i.admin || auth.isAdmin)),
)

async function logout() {
  if (!(await ui.confirm(t('Log out'), t('Log out of this device?'), t('Log out')))) return
  auth.logout()
  router.push({ name: 'login' })
}

onMounted(() => {
  shift.refresh().catch(ui.error)
  auth.refreshSettings().catch(() => {}) // keep the saved settings if the service is busy
})
</script>

<template>
  <div class="flex h-full">
    <!-- menu: fixed column on wide screens, slide-in drawer on phones -->
    <div v-if="drawerOpen" class="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" @click="drawerOpen = false" />
    <aside
      :class="[
        'fixed inset-y-0 left-0 z-30 flex flex-col border-r border-line bg-white transition-all duration-200 lg:static',
        collapsed ? 'lg:w-[76px]' : 'lg:w-64',
        drawerOpen ? 'w-64 translate-x-0' : 'w-64 -translate-x-full lg:translate-x-0',
      ]"
    >
      <div class="flex h-16 items-center gap-3 border-b border-line px-4">
        <img v-if="auth.settings.logo_url" :src="auth.settings.logo_url" alt="" class="size-10 shrink-0 rounded-xl object-contain" />
        <div v-else class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-white"><Store :size="22" /></div>
        <span v-if="!collapsed || drawerOpen" class="truncate font-extrabold">{{ auth.settings.store_name }}</span>
      </div>

      <nav class="flex-1 space-y-1 overflow-y-auto p-3">
        <RouterLink
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          :title="collapsed ? t(item.label) : undefined"
          class="flex items-center gap-3 rounded-xl px-3.5 py-2.5 font-medium text-ink transition hover:bg-page"
          active-class="!bg-primary-soft !text-primary font-bold"
        >
          <component :is="item.icon" :size="20" class="shrink-0" />
          <span v-if="!collapsed || drawerOpen" class="truncate">{{ t(item.label) }}</span>
        </RouterLink>
      </nav>

      <div class="border-t border-line p-3">
        <div class="flex items-center gap-3 px-1">
          <div class="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-soft font-bold text-primary">
            {{ auth.displayName.charAt(0).toUpperCase() }}
          </div>
          <div v-if="!collapsed || drawerOpen" class="min-w-0 flex-1">
            <p class="truncate font-semibold">{{ auth.displayName }}</p>
            <p class="text-xs text-muted capitalize">{{ t(auth.user?.role ?? '') }}</p>
          </div>
          <button v-if="!collapsed || drawerOpen" class="btn-ghost p-2" :title="t('Log out')" @click="logout"><LogOut :size="19" /></button>
        </div>
        <button v-if="collapsed && !drawerOpen" class="btn-ghost mt-2 w-full p-2" :title="t('Log out')" @click="logout"><LogOut :size="19" /></button>
        <button class="btn-ghost mt-2 hidden w-full p-2 lg:flex" :title="collapsed ? t('Expand menu') : t('Collapse menu')" @click="collapsed = !collapsed">
          <component :is="collapsed ? ChevronsRight : ChevronsLeft" :size="19" />
        </button>
      </div>
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <header class="flex h-16 shrink-0 items-center gap-3 border-b border-line bg-white px-4">
        <button class="btn-ghost -ml-2 p-2 lg:hidden" :aria-label="t('Open menu')" @click="drawerOpen = true"><Menu :size="22" /></button>
        <h1 class="flex-1 truncate text-lg font-bold">{{ route.meta.title ? t(route.meta.title) : '' }}</h1>
        <div class="flex rounded-xl bg-page p-1 text-sm font-semibold" role="group" :aria-label="t('Language')">
          <button :class="['rounded-lg px-2.5 py-1', lang === 'en' ? 'bg-white shadow-sm' : 'text-muted']" @click="setLang('en')">EN</button>
          <button :class="['rounded-lg px-2.5 py-1', lang === 'km' ? 'bg-white shadow-sm' : 'text-muted']" @click="setLang('km')">ខ្មែរ</button>
        </div>
        <span class="pill hidden bg-page text-muted sm:inline-flex">1 USD = {{ khr(auth.settings.exchange_rate) }}</span>
        <RouterLink
          v-if="shift.loaded"
          to="/shift"
          :class="['pill', shift.current ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn']"
          :title="shift.current ? t('Your cash drawer shift is open') : t('Open a shift to count your cash drawer')"
        >
          <component :is="shift.current ? LockKeyholeOpen : LockKeyhole" :size="14" />
          {{ shift.current ? t('Shift open') : t('No shift') }}
        </RouterLink>
      </header>
      <main class="min-h-0 flex-1 overflow-y-auto">
        <RouterView />
      </main>
    </div>
  </div>
</template>
