<script setup lang="ts">
import DialogHost from '@/components/DialogHost.vue'
import ToastHost from '@/components/ToastHost.vue'
</script>

<template>
  <RouterView />
  <DialogHost />
  <ToastHost />
</template>
