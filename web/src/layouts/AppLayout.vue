<script setup lang="ts">
import {
  ChartColumn,
  ChevronDown,
  ChevronRight,
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
  Wallet,
  Warehouse,
} from 'lucide-vue-next'
import { type Component, computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { lang, setLang, t } from '@/lib/i18n'
import { khr } from '@/lib/money'
import { REPORT_MENU } from '@/lib/reportDefs'
import type { Permission } from '@/api/types'
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
/** The narrow icon-only menu (wide screens); the phone drawer always shows the full menu. */
const iconsOnly = computed(() => collapsed.value && !drawerOpen.value)

type Badge = 'low' | 'road'
type MenuLink = { to: string; label: string; perm?: Permission | Permission[]; admin?: boolean; section?: string; badge?: Badge }
type MenuItem = MenuLink & { icon: Component; children?: MenuLink[] }
type MenuSection = { heading?: string; items: MenuItem[] }

const MENU: MenuSection[] = [
  { items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, perm: 'reports' }] },
  {
    heading: 'Sell',
    items: [
      { to: '/sell', label: 'POS', icon: ShoppingCart },
      { to: '/sales', label: 'Sales', icon: ReceiptText },
      { to: '/shift', label: 'Shift', icon: Clock },
      { to: '/customers', label: 'Customers', icon: Users },
    ],
  },
  {
    heading: 'Stock',
    items: [
      {
        to: '/products',
        label: 'Products',
        icon: Package,
        children: [
          { to: '/products', label: 'Product list', perm: 'products' },
          { to: '/labels', label: 'Barcode & QR labels', perm: ['products', 'inventory'] },
        ],
      },
      {
        to: '/inventory',
        label: 'Inventory',
        icon: Warehouse,
        perm: 'inventory',
        children: [
          { to: '/inventory', label: 'Stock levels' },
          { to: '/inventory/low', label: 'Low stock', badge: 'low' },
          { to: '/inventory/movements', label: 'Stock movements' },
          { to: '/inventory/transfers', label: 'Stock transfers', badge: 'road' },
          { to: '/inventory/locations', label: 'Branches & warehouses' },
        ],
      },
      { to: '/suppliers', label: 'Suppliers', icon: Truck, perm: 'suppliers' },
    ],
  },
  {
    heading: 'Finance',
    items: [
      { to: '/expenses', label: 'Expenses', icon: Wallet, perm: 'expenses' },
      {
        to: '/reports',
        label: 'Reports',
        icon: ChartColumn,
        perm: 'reports',
        children: [
          { to: '/reports', label: 'Overview' },
          ...REPORT_MENU.map(([kind, label, section]) => ({ to: `/reports/${kind}`, label, section })),
        ],
      },
    ],
  },
  {
    heading: 'Admin',
    items: [
      { to: '/settings', label: 'Store settings', icon: Store, admin: true },
      {
        to: '/users',
        label: 'Staff',
        icon: UserCog,
        children: [
          { to: '/users', label: 'Staff accounts', perm: 'staff' },
          { to: '/permissions', label: 'Roles & permissions', admin: true },
        ],
      },
      { to: '/activity', label: 'Activity log', icon: History, admin: true },
    ],
  },
]

function allowed(link: MenuLink) {
  const perms = link.perm === undefined ? [] : Array.isArray(link.perm) ? link.perm : [link.perm]
  return (!perms.length || perms.some((p) => auth.can(p))) && (!link.admin || auth.isAdmin)
}

/** The menu this user may see; a group whose sub-items are all hidden disappears, and so does an empty section. */
const sections = computed(() =>
  MENU.map((section) => ({
    ...section,
    items: section.items
      .filter(allowed)
      .map((i) => (i.children ? { ...i, children: i.children.filter(allowed) } : i))
      .filter((i) => !i.children || i.children.length)
      .map((i) => (i.children ? { ...i, to: i.children[0]!.to } : i)),
  })).filter((section) => section.items.length),
)

const onPage = (link: MenuLink) => route.path === link.to
function groupActive(item: MenuItem) {
  return !!item.children?.some((c) => onPage(c) || route.path.startsWith(`${c.to}/`))
}

/** One group open at a time: the one of the page shown, or the one opened by hand since. */
const openGroup = ref<string | null>(null)
watch(
  () => route.path,
  () => {
    const active = sections.value.flatMap((s) => s.items).find(groupActive)
    if (active) openGroup.value = active.label
  },
  { immediate: true },
)
function toggle(item: MenuItem) {
  openGroup.value = openGroup.value === item.label ? null : item.label
}

/** Where you are, for the top bar: "Reports › Sales by product". */
const crumbs = computed(() => {
  for (const item of sections.value.flatMap((s) => s.items)) {
    const child = item.children?.find(onPage)
    if (child) return child.label === item.label ? [item.label] : [item.label, child.label]
  }
  return route.meta.title ? [route.meta.title] : []
})

// counts beside the menu entries: products running low, transfers on the road
const counts = ref<Record<Badge, number>>({ low: 0, road: 0 })
let countedAt = 0
async function refreshCounts(force = false) {
  if (!auth.can('inventory') || (!force && Date.now() - countedAt < 30_000)) return
  countedAt = Date.now()
  try {
    const [low, road] = await Promise.all([
      api.get<unknown[]>('/inventory/low-stock'),
      api.get<unknown[]>('/transfers', { status: 'in_transit' }),
    ])
    counts.value = { low: low.length, road: road.length }
  } catch {
    // the counts are only a hint
  }
}
watch(() => route.path, (path) => refreshCounts(path.startsWith('/inventory')))
const groupCount = (item: MenuItem) => (item.children ?? []).reduce((sum, c) => sum + (c.badge ? counts.value[c.badge] : 0), 0)

// keep the page shown in view in a long menu
const nav = ref<HTMLElement>()
async function showCurrent() {
  await nextTick()
  nav.value?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest' })
}
watch(() => route.fullPath, showCurrent)

// icon-only menu: pointing at an icon shows its name, and the pages of a group
const flyout = ref<{ item: MenuItem; top: number } | null>(null)
const flyoutEl = ref<HTMLElement>()
let flyoutTimer: ReturnType<typeof setTimeout> | undefined
function showFlyout(item: MenuItem, e: Event) {
  if (!iconsOnly.value) return
  clearTimeout(flyoutTimer)
  flyout.value = { item, top: (e.currentTarget as HTMLElement).getBoundingClientRect().top }
  // a long list near the bottom moves up so all of it shows
  nextTick(() => {
    const height = flyoutEl.value?.offsetHeight ?? 0
    if (flyout.value && flyout.value.top + height > innerHeight - 8) flyout.value.top = Math.max(8, innerHeight - height - 8)
  })
}
function keepFlyout() {
  clearTimeout(flyoutTimer)
}
function hideFlyout() {
  clearTimeout(flyoutTimer)
  flyoutTimer = setTimeout(() => (flyout.value = null), 150)
}
watch([() => route.fullPath, iconsOnly], () => (flyout.value = null))

const roleClass = computed(
  () => ({ admin: 'bg-violet-100 text-violet-700', manager: 'bg-primary-soft text-primary', cashier: 'bg-white text-muted' })[auth.user?.role ?? 'cashier'],
)

async function logout() {
  if (!(await ui.confirm(t('Log out'), t('Log out of this device?'), t('Log out')))) return
  auth.logout()
  router.push({ name: 'login' })
}

onMounted(() => {
  showCurrent()
  refreshCounts(true)
  shift.refresh().catch(ui.error)
  auth.refreshSettings().catch(() => {}) // keep the saved settings if the service is busy
  auth.refreshPermissions().catch(() => {})
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
        <div v-else class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-indigo-500 text-white shadow-sm shadow-primary/30">
          <Store :size="21" />
        </div>
        <div v-if="!iconsOnly" class="min-w-0">
          <p class="truncate leading-tight font-extrabold">{{ auth.settings.store_name }}</p>
          <p class="text-xs text-muted">{{ t('Point of sale') }}</p>
        </div>
      </div>

      <nav ref="nav" :class="['flex-1 overflow-y-auto py-3', iconsOnly ? 'px-2' : 'px-3']" :aria-label="t('Menu')">
        <div v-for="(section, si) in sections" :key="section.heading ?? si" :class="['space-y-0.5', si > 0 && !iconsOnly && 'mt-5']">
          <!-- section heading; a thin line in the icon-only menu -->
          <p v-if="section.heading && !iconsOnly" class="px-3 pb-1.5 text-[10.5px] font-bold tracking-[0.12em] text-muted/80 uppercase">
            {{ t(section.heading) }}
          </p>
          <hr v-else-if="si > 0" class="mx-3 my-2.5 border-line" />

          <template v-for="item in section.items" :key="item.label">
            <!-- group with sub-items (one open at a time) -->
            <template v-if="item.children && !iconsOnly">
              <button
                type="button"
                :class="['group flex w-full items-center gap-3 rounded-xl px-2 py-1.5 font-medium transition hover:bg-page', groupActive(item) ? 'text-primary' : 'text-ink']"
                :aria-expanded="openGroup === item.label"
                @click="toggle(item)"
              >
                <span :class="['flex size-8 shrink-0 items-center justify-center rounded-lg transition', groupActive(item) ? 'bg-primary-soft text-primary' : 'bg-page text-muted group-hover:text-ink']">
                  <component :is="item.icon" :size="18" />
                </span>
                <span class="flex-1 truncate text-left">{{ t(item.label) }}</span>
                <span v-if="groupCount(item) && openGroup !== item.label" class="rounded-full bg-warn-soft px-2 text-xs font-bold text-warn">{{ groupCount(item) }}</span>
                <ChevronDown :size="16" :class="['shrink-0 text-muted transition-transform duration-200', openGroup === item.label && 'rotate-180']" />
              </button>
              <div v-if="openGroup === item.label" class="relative mt-0.5 mb-1 ml-6 space-y-0.5 border-l border-line pl-2.5" data-submenu>
                <template v-for="(child, ci) in item.children" :key="child.to">
                  <p v-if="child.section && child.section !== item.children[ci - 1]?.section" class="px-2.5 pt-2 pb-0.5 text-[10px] font-bold tracking-[0.12em] text-muted/80 uppercase">
                    {{ t(child.section) }}
                  </p>
                  <RouterLink v-slot="{ href, navigate, isExactActive }" :to="child.to" custom>
                    <a
                      :href="href"
                      :aria-current="isExactActive ? 'page' : undefined"
                      :class="['group/sub flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition', isExactActive ? 'bg-primary-soft font-semibold text-primary' : 'text-ink/80 hover:bg-page hover:text-ink']"
                      @click="navigate"
                    >
                      <span :class="['size-1.5 shrink-0 rounded-full transition', isExactActive ? 'bg-primary ring-4 ring-primary/15' : 'bg-line group-hover/sub:bg-muted']" />
                      <span class="flex-1 truncate">{{ t(child.label) }}</span>
                      <span v-if="child.badge && counts[child.badge]" class="rounded-full bg-warn-soft px-2 text-xs font-bold text-warn">{{ counts[child.badge] }}</span>
                    </a>
                  </RouterLink>
                </template>
              </div>
            </template>
            <!-- single page, or a group in the icon-only menu (opens its first page; pointing shows the rest) -->
            <RouterLink v-else v-slot="{ href, navigate, isActive }" :to="item.to" custom>
              <a
                :href="href"
                :aria-label="t(item.label)"
                :aria-current="isActive && !item.children ? 'page' : undefined"
                :class="[
                  'group relative flex items-center gap-3 rounded-xl py-1.5 font-medium transition',
                  iconsOnly ? 'justify-center px-0' : 'px-2',
                  isActive || groupActive(item) ? 'bg-primary-soft font-semibold text-primary' : 'text-ink hover:bg-page',
                ]"
                @click="navigate"
                @mouseenter="showFlyout(item, $event)"
                @mouseleave="hideFlyout"
                @focus="showFlyout(item, $event)"
                @blur="hideFlyout"
              >
                <span
                  :class="[
                    'flex size-8 shrink-0 items-center justify-center rounded-lg transition',
                    isActive || groupActive(item) ? 'bg-primary text-white shadow-sm shadow-primary/30' : 'bg-page text-muted group-hover:text-ink',
                  ]"
                >
                  <component :is="item.icon" :size="18" />
                </span>
                <span v-if="!iconsOnly" class="truncate">{{ t(item.label) }}</span>
                <span v-if="iconsOnly && groupCount(item)" class="absolute top-1 right-2 size-2 rounded-full bg-warn ring-2 ring-white" />
              </a>
            </RouterLink>
          </template>
        </div>
      </nav>

      <!-- icon-only menu: name and pages of the icon pointed at -->
      <div
        v-if="flyout"
        ref="flyoutEl"
        class="fixed left-[84px] z-40 min-w-52 rounded-xl border border-line bg-white p-1.5 shadow-xl"
        :style="{ top: `${flyout.top}px` }"
        data-flyout
        @mouseenter="keepFlyout"
        @mouseleave="hideFlyout"
      >
        <RouterLink v-if="!flyout.item.children" :to="flyout.item.to" class="block rounded-lg px-3 py-2 font-semibold hover:bg-page">{{ t(flyout.item.label) }}</RouterLink>
        <template v-else>
          <p class="px-3 pt-1.5 pb-1 text-xs font-bold tracking-wider text-muted uppercase">{{ t(flyout.item.label) }}</p>
          <div class="max-h-[70vh] overflow-y-auto">
            <template v-for="(child, ci) in flyout.item.children" :key="child.to">
              <p v-if="child.section && child.section !== flyout.item.children[ci - 1]?.section" class="px-3 pt-2 pb-0.5 text-[10.5px] font-bold tracking-wider text-muted uppercase">
                {{ t(child.section) }}
              </p>
              <RouterLink :to="child.to" class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium hover:bg-page" exact-active-class="!bg-primary-soft !text-primary font-bold">
                <span class="flex-1">{{ t(child.label) }}</span>
                <span v-if="child.badge && counts[child.badge]" class="rounded-full bg-warn-soft px-2 text-xs font-bold text-warn">{{ counts[child.badge] }}</span>
              </RouterLink>
            </template>
          </div>
        </template>
      </div>

      <div class="border-t border-line p-3">
        <div :class="['flex items-center gap-3 rounded-xl', !iconsOnly && 'bg-page p-2']">
          <div class="flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary to-indigo-500 font-bold text-white">
            {{ auth.displayName.charAt(0).toUpperCase() }}
          </div>
          <div v-if="!iconsOnly" class="min-w-0 flex-1">
            <p class="truncate text-sm font-semibold">{{ auth.displayName }}</p>
            <span :class="['inline-block rounded-md px-1.5 text-[11px] font-semibold capitalize', roleClass]">{{ t(auth.user?.role ?? '') }}</span>
          </div>
          <button v-if="!iconsOnly" class="btn-ghost p-2" :title="t('Log out')" @click="logout"><LogOut :size="18" /></button>
        </div>
        <button v-if="iconsOnly" class="btn-ghost mt-2 w-full p-2" :title="t('Log out')" @click="logout"><LogOut :size="19" /></button>
        <button class="btn-ghost mt-2 hidden w-full p-1.5 text-muted lg:flex" :title="collapsed ? t('Expand menu') : t('Collapse menu')" @click="collapsed = !collapsed">
          <component :is="collapsed ? ChevronsRight : ChevronsLeft" :size="18" />
        </button>
      </div>
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <header class="flex h-16 shrink-0 items-center gap-3 border-b border-line bg-white px-4">
        <button class="btn-ghost -ml-2 p-2 lg:hidden" :aria-label="t('Open menu')" @click="drawerOpen = true"><Menu :size="22" /></button>
        <h1 class="flex min-w-0 flex-1 items-center gap-1.5 text-lg font-bold">
          <template v-for="(crumb, i) in crumbs" :key="crumb">
            <span v-if="i < crumbs.length - 1" class="hidden shrink-0 font-semibold text-muted sm:inline">{{ t(crumb) }}</span>
            <ChevronRight v-if="i < crumbs.length - 1" :size="18" class="hidden shrink-0 text-muted sm:inline" />
            <span v-else class="truncate">{{ t(crumb) }}</span>
          </template>
        </h1>
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
