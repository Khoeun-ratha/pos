<script setup lang="ts">
import { KeyRound, Lock, Power, UserPlus } from 'lucide-vue-next'
import { onMounted, reactive, ref } from 'vue'

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
    <div class="flex justify-end">
      <button class="btn-primary" @click="creating = true"><UserPlus :size="18" /> {{ t('New user') }}</button>
    </div>
    <div class="card overflow-x-auto">
      <table class="table min-w-[640px]">
        <thead>
          <tr><th>{{ t('User') }}</th><th>{{ t('Role') }}</th><th>{{ t('PIN') }}</th><th>{{ t('Status') }}</th><th class="text-right">{{ t('Actions') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <p class="font-semibold">{{ u.full_name || u.username }}</p>
              <p class="text-xs text-muted">{{ u.username }}</p>
            </td>
            <td>
              <select
                :value="u.role"
                :class="['rounded-lg border-0 px-2 py-1 text-xs font-semibold capitalize', roleClass[u.role]]"
                :disabled="u.id === auth.user?.id"
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
              <button class="btn-ghost p-2" :title="t('Set password')" @click="setPassword(u)"><Lock :size="17" /></button>
              <button class="btn-ghost p-2" :title="t('Set PIN')" @click="setPin(u)"><KeyRound :size="17" /></button>
              <button class="btn-ghost p-2" :title="u.is_active ? 'Deactivate' : 'Activate'" :disabled="u.id === auth.user?.id" @click="toggleActive(u)"><Power :size="17" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="creating" :title="t('New user')" width="max-w-md" @close="creating = false">
      <form id="user-form" class="space-y-3" @submit.prevent="create">
        <div><label class="label">{{ t('Username') }}</label><input v-model="form.username" class="input" autocomplete="off" autofocus /></div>
        <div><label class="label">{{ t('Full name') }}</label><input v-model="form.full_name" class="input" /></div>
        <div><label class="label">{{ t('Password (at least 6 characters)') }}</label><input v-model="form.password" class="input" type="password" autocomplete="new-password" /></div>
        <div><label class="label">{{ t('Quick PIN, 4-6 digits (optional)') }}</label><input v-model="form.pin" class="input" type="password" inputmode="numeric" /></div>
        <div>
          <label class="label">{{ t('Role') }}</label>
          <select v-model="form.role" class="input">
            <option value="cashier">{{ t('Cashier — sell, shifts, own sales') }}</option>
            <option value="manager">{{ t('Manager — plus products, stock, reports, approvals') }}</option>
            <option value="admin">{{ t('Admin — everything, settings and users') }}</option>
          </select>
        </div>
      </form>
      <template #footer>
        <button class="btn-outline" @click="creating = false">{{ t('Cancel') }}</button>
        <button class="btn-primary" type="submit" form="user-form">{{ t('Add user') }}</button>
      </template>
    </AppModal>
  </div>
</template>
