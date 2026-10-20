// Coloured picture area for products without photos: one colour and icon per category.
import { Box, Cookie, CupSoda, Package, Sparkles, SprayCan, Wheat } from 'lucide-vue-next'
import type { Component } from 'vue'

export interface Art {
  bg: string
  fg: string
  icon: Component
}

export function categoryArt(category: string | null | undefined): Art {
  const name = (category ?? '').toLowerCase()
  if (name.includes('drink')) return { bg: '#dbeafe', fg: '#1d4ed8', icon: CupSoda }
  if (name.includes('snack')) return { bg: '#fef3c7', fg: '#b45309', icon: Cookie }
  if (name.includes('grocer')) return { bg: '#dcfce7', fg: '#15803d', icon: Wheat }
  if (name.includes('care')) return { bg: '#fce7f3', fg: '#be185d', icon: Sparkles }
  if (name.includes('house')) return { bg: '#ede9fe', fg: '#6d28d9', icon: SprayCan }
  if (name) return { bg: '#e0f2fe', fg: '#0369a1', icon: Box }
  return { bg: '#e2e8f0', fg: '#475569', icon: Package }
}
