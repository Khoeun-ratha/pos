<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { categoryArt } from '@/lib/art'

/** The product's photo, or a coloured category icon when it has none (or the photo cannot load). */
const props = withDefaults(defineProps<{ category: string | null | undefined; image?: string | null; size?: number; alt?: string }>(), {
  size: 40,
  image: null,
  alt: '',
})
const art = computed(() => categoryArt(props.category))
const failed = ref(false)
watch(
  () => props.image,
  () => (failed.value = false),
)
</script>

<template>
  <div class="flex items-center justify-center overflow-hidden" :style="image && !failed ? { background: '#f8fafc' } : { background: art.bg, color: art.fg }">
    <img v-if="image && !failed" :src="image" :alt="alt" loading="lazy" class="size-full object-cover" @error="failed = true" />
    <component :is="art.icon" v-else :size="size" :stroke-width="1.8" />
  </div>
</template>
