<script setup lang="ts">
// The RATHA MART mark: an R drawn as a shopping cart (handle, basket, two amber wheels). The same drawing as
// public/favicon.svg; public/receipt-logo.svg is its black version for receipt printers.
import { useId } from 'vue'

const gradient = useId()
</script>

<template>
  <svg viewBox="0 0 64 64" role="img" aria-label="RATHA MART">
    <defs>
      <linearGradient :id="gradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#3b82f6" />
        <stop offset="1" stop-color="#1e40af" />
      </linearGradient>
    </defs>
    <rect width="64" height="64" rx="16" :fill="`url(#${gradient})`" />
    <g fill="none" stroke="#fff" stroke-width="5.4" stroke-linecap="round" stroke-linejoin="round">
      <path d="M17 14h8v27h22" />
      <path d="M25 14h12.5a8.5 8.5 0 0 1 0 17H25" />
      <path d="M35 31l11 10" />
    </g>
    <circle cx="28" cy="49.5" r="3.7" fill="#fbbf24" />
    <circle cx="44" cy="49.5" r="3.7" fill="#fbbf24" />
  </svg>
</template>
