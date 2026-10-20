<script setup lang="ts">
import { UserPlus } from 'lucide-vue-next'
import { onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { Customer } from '@/api/types'
import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { useUi } from '@/stores/ui'

const emit = defineEmits<{ close: []; pick: [customer: Customer] }>()
const ui = useUi()
const query = ref('')
const customers = ref<Customer[]>([])
let timer: ReturnType<typeof setTimeout> | undefined

async function search() {
  try {
    customers.value = await api.get<Customer[]>('/customers', { q: query.value.trim() })
  } catch (e) {
    ui.error(e)
  }
}

watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 250)
})
onMounted(search)

async function create() {
  const name = await ui.prompt({ title: 'New customer', label: 'Name', initial: query.value.trim() })
  if (!name?.trim()) return
  const phone = await ui.prompt({ title: 'New customer', label: 'Phone (optional)', inputmode: 'tel' })
  try {
    emit('pick', await api.post<Customer>('/customers', { name: name.trim(), phone: phone?.trim() || null }))
  } catch (e) {
    ui.error(e)
  }
}
</script>

<template>
  <AppModal :title="t('Choose customer')" @close="emit('close')">
    <div class="mb-3 flex gap-2">
      <input v-model="query" class="input" :placeholder="t('Search name or phone')" autofocus />
      <button class="btn-outline shrink-0" @click="create"><UserPlus :size="18" /> {{ t('New') }}</button>
    </div>
    <ul class="divide-y divide-line rounded-xl border border-line">
      <li v-if="!customers.length" class="p-6 text-center text-muted">{{ t('No customers found') }}</li>
      <li v-for="c in customers" :key="c.id">
        <button class="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-page" @click="emit('pick', c)">
          <span class="flex size-9 items-center justify-center rounded-full bg-primary-soft font-bold text-primary">{{ c.name.charAt(0) }}</span>
          <span class="flex-1">
            <span class="block font-semibold">{{ c.name }}</span>
            <span class="text-sm text-muted">{{ c.phone }}</span>
          </span>
          <span class="pill bg-page text-muted">{{ t('{n} pts', { n: c.points }) }}</span>
        </button>
      </li>
    </ul>
  </AppModal>
</template>
