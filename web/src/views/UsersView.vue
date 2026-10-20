<script setup lang="ts">
import { KeyRound, Lock, Pencil, Power, Search, ShieldCheck, UserPlus } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref } from 'vue'

import { api } from '@/api/client'
import type { Role, User } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'
import { t } from '@/lib/i18n'

const auth = useAuth()
const ui = useUi()
const users = ref<User[]>([])
const creating = ref(false)
const form = reactive({ username: '', full_name: '', password: '', pin: '', role: 'cashier' as Role })
const roleClass = { admin: 'bg-violet-50 text-violet-700', manager: 'bg-primary-soft text-primary', cashier: 'bg-page text-muted' }
const query = ref('')
const show = ref<'active' | 'inactive' | 'all'>('active')

/** The admin manages everyone; a manager given "Manage staff" manages the cashiers (the service checks too). */
const canManage = (u: User) => u.id !== auth.user?.id && (auth.isAdmin || u.role === 'cashier')
const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return users.value.filter(
    (u) =>
      (show.value === 'all' || u.is_active === (show.value === 'active')) &&
      (!q || u.username.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q)),
  )
})
const counts = computed(() => {
  const active = users.value.filter((u) => u.is_active)
  return [
    { label: 'Admins', n: active.filter((u) => u.role === 'admin').length, class: roleClass.admin },
    { label: 'Managers', n: active.filter((u) => u.role === 'manager').length, class: roleClass.manager },
    { label: 'Cashiers', n: active.filter((u) => u.role === 'cashier').length, class: roleClass.cashier },
    { label: 'Inactive', n: users.value.length - active.length, class: 'bg-rose-50 text-price' },
  ]
})

async function load() {
  try {
    users.value = await api.get<User[]>('/users')
  } catch (e) {
    ui.error(e)
  }
}

async function update(user: User, changes: Record<string, unknown>, done: string) {
  try {
    await api.patch(`/users/${user.id}`, changes)
    ui.toast(done, 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

async function create() {
  try {
    await api.post('/users', { ...form, pin: form.pin || null })
    creating.value = false
    Object.assign(form, { username: '', full_name: '', password: '', pin: '', role: 'cashier' })
    ui.toast('User added', 'success')
    load()
  } catch (e) {
    ui.error(e)
  }
}

async function rename(user: User) {
  const name = await ui.prompt({ title: t('Name of {name}', { name: user.username }), label: 'Full name', initial: user.full_name })
  if (name !== null && name.trim() !== user.full_name) update(user, { full_name: name.trim() }, 'Name changed')
}

async function setPassword(user: User) {
  const password = await ui.prompt({ title: t('Password for {name}', { name: user.username }), label: 'New password (at least 6 characters)', password: true })
  if (password) update(user, { password }, 'Password changed')
}

async function setPin(user: User) {
  const pin = await ui.prompt({ title: t('PIN for {name}', { name: user.username }), label: 'New PIN (4-6 digits)', password: true, inputmode: 'numeric' })
  if (pin) update(user, { pin }, 'PIN changed')
}

async function toggleActive(user: User) {
  const verb = t(user.is_active ? 'Deactivate' : 'Activate')
  if (await ui.confirm(`${verb} ${user.username}?`, user.is_active ? 'They will not be able to log in.' : 'They will be able to log in again.', verb, user.is_active)) {
    update(user, { is_active: !user.is_active }, t(user.is_active ? '{name} deactivated' : '{name} activated', { name: user.username }))
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 p-4 lg:p-6">
    <div class="flex flex-wrap gap-2">
      <span v-for="c in counts" :key="c.label" :class="['pill px-3 py-1.5 text-sm', c.class]">{{ t(c.label) }} · {{ c.n }}</span>
    </div>
    <div class="card flex flex-wrap items-center gap-2 p-3">
      <div class="relative min-w-48 flex-1">
        <Search :size="17" class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
        <input v-model="query" class="input pl-9" :placeholder="t('Search name or username')" />
      </div>
      <div class="flex gap-1 rounded-xl bg-page p-1">
        <button
          v-for="s in ['active', 'inactive', 'all'] as const"
          :key="s"
          :class="['rounded-lg px-3 py-1.5 text-sm font-semibold', show === s ? 'bg-white text-primary shadow-sm' : 'text-muted']"
          @click="show = s"
        >
          {{ t({ active: 'Active', inactive: 'Inactive', all: 'All' }[s]) }}
        </button>
      </div>
      <RouterLink v-if="auth.isAdmin" to="/permissions" class="btn-outline"><ShieldCheck :size="18" /> {{ t('Roles & permissions') }}</RouterLink>
      <button class="btn-primary" @click="creating = true"><UserPlus :size="18" /> {{ auth.isAdmin ? t('New user') : t('New cashier') }}</button>
    </div>
    <p v-if="!auth.isAdmin" class="px-1 text-sm text-muted">{{ t('You can add cashiers, reset their password or PIN and deactivate them. Managers and admins are managed by the admin.') }}</p>
    <div class="card overflow-x-auto">
      <table class="table min-w-[640px]">
        <thead>
          <tr><th>{{ t('User') }}</th><th>{{ t('Role') }}</th><th>{{ t('PIN') }}</th><th>{{ t('Status') }}</th><th class="text-right">{{ t('Actions') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in visible" :key="u.id" :class="!u.is_active && 'opacity-60'">
            <td>
              <p class="font-semibold">{{ u.full_name || u.username }}</p>
              <p class="text-xs text-muted">{{ u.username }}</p>
            </td>
            <td>
              <select
                :value="u.role"
                :class="['rounded-lg border-0 px-2 py-1 text-xs font-semibold capitalize', roleClass[u.role]]"
                :disabled="!auth.isAdmin || u.id === auth.user?.id"
                @change="update(u, { role: ($event.target as HTMLSelectElement).value }, 'Role changed')"
              >
                <option value="cashier">{{ t('cashier') }}</option>
                <option value="manager">{{ t('manager') }}</option>
                <option value="admin">{{ t('admin') }}</option>
              </select>
            </td>
            <td>{{ u.has_pin ? t('Yes') : '—' }}</td>
            <td><span :class="['pill', u.is_active ? 'bg-ok-soft text-ok' : 'bg-rose-50 text-price']">{{ u.is_active ? t('Active') : t('Inactive') }}</span></td>
            <td class="text-right whitespace-nowrap">
              <button class="btn-ghost p-2" :title="t('Change name')" :disabled="!canManage(u)" @click="rename(u)"><Pencil :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Set password')" :disabled="!canManage(u)" @click="setPassword(u)"><Lock :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Set PIN')" :disabled="!canManage(u)" @click="setPin(u)"><KeyRound :size="17" /></button>
              <button class="btn-ghost p-2" :title="t(u.is_active ? 'Deactivate' : 'Activate')" :disabled="!canManage(u)" @click="toggleActive(u)"><Power :size="17" /></button>
            </td>
          </tr>
          <tr v-if="!visible.length">
            <td colspan="5" class="py-8 text-center text-muted">{{ t('Nobody found') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="creating" :title="auth.isAdmin ? t('New user') : t('New cashier')" width="max-w-md" @close="creating = false">
      <form id="user-form" class="space-y-3" @submit.prevent="create">
        <div><label class="label">{{ t('Username') }}</label><input v-model="form.username" class="input" autocomplete="off" autofocus /></div>
        <div><label class="label">{{ t('Full name') }}</label><input v-model="form.full_name" class="input" /></div>
        <div><label class="label">{{ t('Password (at least 6 characters)') }}</label><input v-model="form.password" class="input" type="password" autocomplete="new-password" /></div>
        <div><label class="label">{{ t('Quick PIN, 4-6 digits (optional)') }}</label><input v-model="form.pin" class="input" type="password" inputmode="numeric" /></div>
        <div v-if="auth.isAdmin">
          <label class="label">{{ t('Role') }}</label>
          <select v-model="form.role" class="input">
            <option value="cashier">{{ t('Cashier') }}</option>
            <option value="manager">{{ t('Manager') }}</option>
            <option value="admin">{{ t('Admin — everything, settings and users') }}</option>
          </select>
          <p class="mt-1 text-xs text-muted">
            {{ t('What cashiers and managers may do is set in') }}
            <RouterLink to="/permissions" class="font-semibold text-primary hover:underline">{{ t('Roles & permissions') }}</RouterLink>
          </p>
        </div>
      </form>
      <template #footer>
        <button class="btn-outline" @click="creating = false">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="user-form">{{ t('Add user') }}</button>
      </template>
    </AppModal>
  </div>
</template>
