<script setup lang="ts">
import type { StockMovement } from '@/api/types'
import { t } from '@/lib/i18n'
import { dateTime, usd } from '@/lib/money'

/** Stock movement rows; `showProduct` adds the product column (the history of one product leaves it out),
 *  `showLocation` the place (`mainName` for the main shop). */
defineProps<{ movements: StockMovement[]; showProduct?: boolean; showLocation?: boolean; mainName?: string }>()

const KINDS: Record<string, string> = {
  sale: 'Sale',
  refund: 'Refund',
  stock_in: 'Received',
  adjustment: 'Adjustment',
  count: 'Stock count',
  write_off: 'Write-off',
  transfer_out: 'Transfer sent',
  transfer_in: 'Transfer received',
}
</script>

<template>
  <div class="overflow-x-auto">
    <table :class="['table', showProduct ? 'min-w-[820px]' : 'min-w-[640px]']">
      <thead>
        <tr>
          <th>{{ t('When') }}</th><th v-if="showProduct">{{ t('Product') }}</th><th v-if="showLocation">{{ t('Place') }}</th><th>{{ t('Type') }}</th>
          <th class="text-right">{{ t('Change') }}</th><th class="text-right">{{ t('Balance') }}</th>
          <th class="text-right">{{ t('Unit cost') }}</th><th>{{ t('Details') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in movements" :key="m.id">
          <td class="whitespace-nowrap text-muted">{{ dateTime(m.created_at) }}</td>
          <td v-if="showProduct" class="font-semibold">{{ m.product_name }}</td>
          <td v-if="showLocation" class="text-muted">{{ m.location_name ?? mainName }}</td>
          <td>{{ t(KINDS[m.kind] ?? m.kind) }}</td>
          <td :class="['text-right font-semibold', m.change > 0 ? 'text-ok' : 'text-price']">{{ m.change > 0 ? '+' : '' }}{{ m.change }}</td>
          <td class="text-right">{{ m.balance }}</td>
          <td class="text-right text-muted">{{ m.unit_cost === null ? '' : usd(m.unit_cost) }}</td>
          <td class="text-muted">{{ [m.supplier_name, m.reference, m.note].filter(Boolean).join(' · ') }}</td>
        </tr>
        <tr v-if="!movements.length">
          <td :colspan="6 + (showProduct ? 1 : 0) + (showLocation ? 1 : 0)" class="py-8 text-center text-muted">{{ t('No stock movements yet') }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
