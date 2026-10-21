<script setup lang="ts">
import { ImagePlus, Save, Store, Trash2 } from 'lucide-vue-next'
import { reactive, ref } from 'vue'

import { api } from '@/api/client'
import type { StoreSettings } from '@/api/types'
import RegisterSettings from '@/components/RegisterSettings.vue'
import { t } from '@/lib/i18n'
import { khr, parseHundredths, parseWhole } from '@/lib/money'
import { useAuth } from '@/stores/auth'
import { useUi } from '@/stores/ui'

const auth = useAuth()
const ui = useUi()
const s = auth.settings
const form = reactive({
  store_name: s.store_name,
  store_address: s.store_address,
  store_phone: s.store_phone,
  receipt_footer: s.receipt_footer,
  exchange_rate: String(s.exchange_rate),
  tax: String(s.tax_rate_bp / 100),
  tax_inclusive: s.tax_inclusive,
  allow_negative_stock: s.allow_negative_stock,
  loyalty_points_per_usd: String(s.loyalty_points_per_usd),
})
const busy = ref(false)
const logoInput = ref<HTMLInputElement>()

async function save() {
  const rate = parseWhole(form.exchange_rate)
  const tax = parseHundredths(form.tax) // 10 -> 1000 basis points
  if (!rate || tax === null || tax > 10000) return ui.toast(t('Check the exchange rate and VAT %'), 'error')
  busy.value = true
  try {
    const body: Omit<StoreSettings, 'logo_url'> = {
      store_name: form.store_name.trim(),
      store_address: form.store_address.trim(),
      store_phone: form.store_phone.trim(),
      receipt_footer: form.receipt_footer.trim(),
      exchange_rate: rate,
      tax_rate_bp: tax,
      tax_inclusive: form.tax_inclusive,
      allow_negative_stock: form.allow_negative_stock,
      loyalty_points_per_usd: parseWhole(form.loyalty_points_per_usd) ?? 1,
    }
    await api.put('/settings', body)
    await auth.refreshSettings()
    ui.toast(t('Settings saved'), 'success')
  } catch (e) {
    ui.error(e)
  } finally {
    busy.value = false
  }
}

async function uploadLogo(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) return ui.toast(t('Choose a photo (JPG, PNG or WebP)'), 'error')
  try {
    await api.upload('/settings/logo', file)
    await auth.refreshSettings()
    ui.toast(t('Logo saved'), 'success')
  } catch (e) {
    ui.error(e)
  } finally {
    logoInput.value!.value = ''
  }
}

async function removeLogo() {
  if (!(await ui.confirm(t('Remove logo'), t('Remove the shop logo?'), t('Remove'), true))) return
  try {
    await api.delete('/settings/logo')
    await auth.refreshSettings()
  } catch (e) {
    ui.error(e)
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-5 p-4 lg:p-6">
  <form class="space-y-5" @submit.prevent="save">
    <p v-if="!auth.isAdmin" class="rounded-xl bg-warn-soft px-4 py-3 text-amber-900">{{ t('Only the admin can change these settings.') }}</p>
    <fieldset :disabled="!auth.isAdmin" class="space-y-5">
      <div class="card space-y-3 p-5">
        <h2 class="font-bold">{{ t('Store & receipt') }}</h2>
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-line bg-page">
            <img v-if="auth.settings.logo_url" :src="auth.settings.logo_url" :alt="t('Shop logo')" class="size-full object-contain" />
            <Store v-else :size="30" class="text-muted" />
          </div>
          <div class="space-y-2">
            <p class="text-sm text-muted">{{ t('Shown in the menu and printed at the top of receipts.') }}</p>
            <div v-if="auth.isAdmin" class="flex flex-wrap gap-2">
              <button type="button" class="btn-outline py-2" @click="logoInput?.click()">
                <ImagePlus :size="17" /> {{ auth.settings.logo_url ? t('Replace logo') : t('Upload logo') }}
              </button>
              <button v-if="auth.settings.logo_url" type="button" class="btn-ghost py-2 text-price" @click="removeLogo"><Trash2 :size="17" /> {{ t('Remove') }}</button>
            </div>
          </div>
          <input ref="logoInput" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="uploadLogo" />
        </div>
        <div><label class="label">{{ t('Store name') }}</label><input v-model="form.store_name" class="input" /></div>
        <div class="grid gap-3 sm:grid-cols-2">
          <div><label class="label">{{ t('Address') }}</label><input v-model="form.store_address" class="input" /></div>
          <div><label class="label">{{ t('Phone') }}</label><input v-model="form.store_phone" class="input" /></div>
        </div>
        <div><label class="label">{{ t('Receipt footer') }}</label><input v-model="form.receipt_footer" class="input" /></div>
      </div>
      <div class="card space-y-3 p-5">
        <h2 class="font-bold">{{ t('Money & tax') }}</h2>
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label class="label">{{ t('Exchange rate (riel per 1 USD)') }}</label>
            <input v-model="form.exchange_rate" class="input" inputmode="numeric" />
            <p class="mt-1 text-xs text-muted">$1.00 = {{ khr(parseWhole(form.exchange_rate) ?? 0) }}</p>
          </div>
          <div><label class="label">{{ t('VAT %') }}</label><input v-model="form.tax" class="input" inputmode="decimal" /></div>
        </div>
        <label class="flex items-center gap-2"><input v-model="form.tax_inclusive" type="checkbox" class="size-4 accent-primary" /> {{ t('Prices already include VAT') }}</label>
      </div>
      <div class="card space-y-3 p-5">
        <h2 class="font-bold">{{ t('Stock & loyalty') }}</h2>
        <label class="flex items-center gap-2"><input v-model="form.allow_negative_stock" type="checkbox" class="size-4 accent-primary" /> {{ t('Allow selling when stock shows 0') }}</label>
        <div class="max-w-xs"><label class="label">{{ t('Loyalty points per 1 USD') }}</label><input v-model="form.loyalty_points_per_usd" class="input" inputmode="numeric" /></div>
      </div>
      <button v-if="auth.isAdmin" class="btn-primary px-6 py-3" :disabled="busy"><Save :size="18" /> {{ t('Save settings') }}</button>
    </fieldset>
  </form>
  <RegisterSettings />
  </div>
</template>
