// Barcode scanners (USB / Bluetooth "keyboard wedge") type the code very fast and press Enter (some press Tab).
// useBarcodeScanner tells such a burst apart from a person typing, wherever the focus is, and hands over the code.
import { onBeforeUnmount, onMounted, ref } from 'vue'

import type { Product } from '@/api/types'

/** What the till did with a scanned code, shown in the camera window. */
export interface ScanOutcome {
  ok: boolean
  message: string
}

/** Longest pause between two keys of one scan. Scanners send a key every 1-30 ms; people are much slower. */
const MAX_GAP_MS = 50
const MIN_LENGTH = 4

/** The key's place on the keyboard, so a scan reads the same with the Khmer keyboard layout switched on. */
function keyChar(e: KeyboardEvent): string | null {
  const code = e.code
  if (/^Digit\d$/.test(code)) return code.slice(5)
  if (/^Numpad\d$/.test(code)) return code.slice(6)
  if (/^Key[A-Z]$/.test(code)) return e.shiftKey ? code.slice(3) : code.slice(3).toLowerCase()
  const symbols: Record<string, string> = { Minus: '-', NumpadSubtract: '-', Period: '.', NumpadDecimal: '.', Slash: '/', Space: ' ' }
  if (code in symbols) return symbols[code]!
  return e.key.length === 1 ? e.key : null
}

function editable(el: EventTarget | null): el is HTMLInputElement | HTMLTextAreaElement {
  return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
}

/** Calls onScan(code) for every scan while enabled() is true. A scan that landed in a text box is taken back out of it. */
export function useBarcodeScanner(onScan: (code: string) => void, enabled: () => boolean) {
  let buffer = ''
  let last = 0
  let target: HTMLInputElement | HTMLTextAreaElement | null = null
  let valueBefore = ''

  function onKey(e: KeyboardEvent) {
    if (e.ctrlKey || e.altKey || e.metaKey || e.isComposing) return
    const now = performance.now()
    const gap = now - last
    last = now

    if (e.key === 'Enter' || e.key === 'Tab') {
      const code = buffer.trim()
      const isScan = gap <= MAX_GAP_MS && code.length >= MIN_LENGTH
      buffer = ''
      if (!isScan || !enabled()) return
      // stop the Enter from also pressing the focused button or submitting a form
      e.preventDefault()
      e.stopPropagation()
      if (target && target === e.target) {
        target.value = valueBefore
        target.dispatchEvent(new Event('input', { bubbles: true }))
      }
      onScan(code)
      return
    }

    const char = keyChar(e)
    if (char === null) return
    if (gap > MAX_GAP_MS || !buffer) {
      buffer = ''
      target = editable(e.target) ? e.target : null
      valueBefore = target?.value ?? ''
    }
    buffer += char
  }

  // capture phase: runs before the text box or button that has the focus
  onMounted(() => window.addEventListener('keydown', onKey, true))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
}

/** A scanned or typed code: trimmed, and Khmer digits (typed with the Khmer keyboard on) as 0-9. */
export function cleanCode(raw: string): string {
  return raw.trim().replace(/[០-៩]/g, (d) => String(d.charCodeAt(0) - 0x17e0))
}

/** Scanners may read a UPC-A code (12 digits) that the shop saved as EAN-13 with a leading 0, or the other way round. */
export function codeVariants(raw: string): string[] {
  const code = cleanCode(raw)
  if (/^\d{12}$/.test(code)) return [code, `0${code}`]
  if (/^0\d{12}$/.test(code)) return [code, code.slice(1)]
  return [code]
}

/** The product with this barcode or SKU (SKU ignores upper / lower case). */
export function findByCode(products: Product[], raw: string): Product | undefined {
  const variants = codeVariants(raw)
  const lower = cleanCode(raw).toLowerCase()
  return products.find((p) => (p.barcode && variants.includes(p.barcode)) || (p.sku && p.sku.toLowerCase() === lower))
}

/** "3*8850999320014" or "3x coke": 3 of that item. A lone "3*" waits for the next scan or tap. */
export function splitQty(text: string): { qty: number; rest: string } {
  const m = /^\s*(\d{1,4})\s*[*xX×]\s*(.*)$/.exec(cleanCode(text))
  if (!m) return { qty: 1, rest: text.trim() }
  return { qty: Math.max(1, Number(m[1])), rest: m[2]!.trim() }
}

// ---------- sounds ----------

function storedSound() {
  try {
    return localStorage.getItem('pos.sound') !== 'off'
  } catch {
    return true
  }
}

export const soundOn = ref(storedSound())

export function setSound(on: boolean) {
  soundOn.value = on
  try {
    localStorage.setItem('pos.sound', on ? 'on' : 'off')
  } catch {
    // private window: lasts until the page closes
  }
}

let audio: AudioContext | null = null

/** Short high beep when an item is added; low double buzz when a code is not found. Phones also vibrate. */
export function beep(kind: 'ok' | 'error') {
  try {
    navigator.vibrate?.(kind === 'ok' ? 40 : [90, 60, 90])
  } catch {
    // no vibration motor
  }
  if (!soundOn.value) return
  try {
    audio ??= new AudioContext()
    const tones = kind === 'ok' ? [{ freq: 1760, at: 0, len: 0.07 }] : [{ freq: 220, at: 0, len: 0.14 }, { freq: 220, at: 0.2, len: 0.14 }]
    for (const tone of tones) {
      const osc = audio.createOscillator()
      const gain = audio.createGain()
      osc.type = kind === 'ok' ? 'sine' : 'square'
      osc.frequency.value = tone.freq
      gain.gain.value = 0.12
      osc.connect(gain).connect(audio.destination)
      const start = audio.currentTime + tone.at
      osc.start(start)
      osc.stop(start + tone.len)
    }
  } catch {
    // no sound card / audio blocked: the toast and the cart still show what happened
  }
}
