<script setup lang="ts">
// The RATHA MART mark: a shopping bag with an R. The same drawing as public/favicon.svg;
// public/receipt-logo.svg is its black and white version for receipt printers.
import { useId } from 'vue'

const gradient = useId()
</script>

<template>
  <svg viewBox="0 0 64 64" role="img" aria-label="RATHA MART">
    <defs>
      <linearGradient :id="gradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#3b82f6" />
        <stop offset="1" stop-color="#1d4ed8" />
      </linearGradient>
    </defs>
    <rect width="64" height="64" rx="16" :fill="`url(#${gradient})`" />
    <path d="M22.8 26c0-7.6 4-11.8 9.2-11.8s9.2 4.2 9.2 11.8" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" />
    <path d="M17.6 24h28.8a2 2 0 0 1 2 1.86l1.5 21.6A4.4 4.4 0 0 1 45.5 52h-27a4.4 4.4 0 0 1-4.4-4.54l1.5-21.6a2 2 0 0 1 2-1.86z" fill="#fff" />
    <path d="M27.5 46.5v-15h5.6a4.5 4.5 0 0 1 0 9h-5.6m5.4 0 5 6" fill="none" stroke="#1d4ed8" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="44" cy="30" r="1.9" fill="#f59e0b" />
  </svg>
</template>
