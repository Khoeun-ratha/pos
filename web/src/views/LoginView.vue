<script setup lang="ts">
import { KeyRound, LogIn } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import BrandMark from '@/components/BrandMark.vue'
import BrandName from '@/components/BrandName.vue'
import { useAuth } from '@/stores/auth'
import { t } from '@/lib/i18n'

const auth = useAuth()
const router = useRouter()
const route = useRoute()

const username = ref(localStorage.getItem('pos.lastUser') ?? '')
const secret = ref('')
const usePin = ref(false)
const busy = ref(false)
const error = ref('')

async function submit() {
  if (!username.value.trim() || !secret.value) return
  busy.value = true
  error.value = ''
  try {
    await auth.login(username.value.trim(), secret.value, usePin.value)
    localStorage.setItem('pos.lastUser', username.value.trim())
    router.replace(typeof route.query.next === 'string' ? route.query.next : '/')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    secret.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex min-h-full items-center justify-center p-4">
    <form class="card w-full max-w-sm p-7 shadow-sm" @submit.prevent="submit">
      <div class="mb-6 flex flex-col items-center text-center">
        <img v-if="auth.settings.logo_url" :src="auth.settings.logo_url" alt="" class="mb-4 size-20 rounded-2xl object-contain" />
        <BrandMark v-else class="mb-4 size-20 drop-shadow-md" />
        <h1 class="text-2xl"><BrandName :name="auth.settings.store_name" /></h1>
        <p class="text-muted">{{ t('Sign in to start selling') }}</p>
      </div>

      <label class="label" for="username">{{ t('Username') }}</label>
      <input id="username" v-model="username" class="input mb-4" autocomplete="username" autofocus />

      <div class="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-page p-1">
        <button type="button" :class="['rounded-lg py-2 font-semibold', !usePin ? 'bg-white shadow-sm' : 'text-muted']" @click="usePin = false">{{ t('Password') }}</button>
        <button type="button" :class="['rounded-lg py-2 font-semibold', usePin ? 'bg-white shadow-sm' : 'text-muted']" @click="usePin = true">{{ t('PIN') }}</button>
      </div>
      <label class="label" for="secret">{{ usePin ? 'PIN' : t('Password') }}</label>
      <input
        id="secret"
        v-model="secret"
        class="input mb-4"
        type="password"
        :inputmode="usePin ? 'numeric' : 'text'"
        :autocomplete="usePin ? 'off' : 'current-password'"
      />

      <p v-if="error" class="mb-4 rounded-xl bg-rose-50 px-3 py-2 text-sm text-price">{{ error }}</p>

      <button class="btn-primary w-full py-3" :disabled="busy">
        <component :is="usePin ? KeyRound : LogIn" :size="18" />
        {{ busy ? t('Signing in...') : t('Log in') }}
      </button>
    </form>
  </div>
</template>
