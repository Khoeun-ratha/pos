import { createPinia } from 'pinia'
import { createApp } from 'vue'

import { onSessionExpired } from '@/api/client'
import App from './App.vue'
import { router } from './router'
import { useAuth } from './stores/auth'
import { useUi } from './stores/ui'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

onSessionExpired(() => {
  useAuth().logout()
  useUi().toast('Your login has expired. Please log in again.', 'error') // ToastHost translates it
  router.push({ name: 'login' })
})

app.mount('#app')
