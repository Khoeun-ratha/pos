<script setup lang="ts">
// The shop's name as a wordmark: the last word in the brand blue (RATHA MART).
import { computed } from 'vue'

const props = defineProps<{ name: string }>()
const parts = computed(() => {
  const name = props.name.trim()
  const cut = name.lastIndexOf(' ')
  return cut > 0 ? [name.slice(0, cut), name.slice(cut + 1)] : [name, '']
})
</script>

<template>
  <span class="font-extrabold tracking-wide">{{ parts[1] ? `${parts[0]} ` : parts[0] }}<span v-if="parts[1]" class="text-primary">{{ parts[1] }}</span></span>
</template>
