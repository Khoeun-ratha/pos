<script setup lang="ts">
// Camera scanning for tablets and phones that use the web app. Like the mobile app it stays open and hands every
// code to the till until the cashier taps Done. Browsers allow the camera only on https or on this PC (localhost).
import { CheckCircle2, Flashlight, SwitchCamera, XCircle } from 'lucide-vue-next'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import { t } from '@/lib/i18n'
import { type ScanOutcome } from '@/lib/scanner'

const props = defineProps<{ onScan: (code: string) => Promise<ScanOutcome> }>()
const emit = defineEmits<{ close: [] }>()

/** The same code counts again only after it was out of sight this long: holding an item under the camera adds it once;
 *  a second one of the same product is scanned after the first is taken away. */
const SAME_CODE_GAP_MS = 1000
const FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'qr_code'] as const
/** Only the middle of the picture counts (the frame on screen), so another item on the counter is not read. */
const FRAME = { width: 0.7, height: 0.4 }

interface Detector {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>
}

const video = ref<HTMLVideoElement>()
const error = ref('')
const outcome = ref<ScanOutcome | null>(null)
const added = ref(0)
const hasTorch = ref(false)
const torchOn = ref(false)
const facing = ref<'environment' | 'user'>('environment')

let stream: MediaStream | null = null
let detector: Detector | null = null
let timer = 0
let busy = false
let lastCode = ''
let lastSeen = 0
let stopped = false
const canvas = document.createElement('canvas')

/** The browser's own detector when it has one (Chrome on Android); otherwise ZXing, shipped with the app. */
async function makeDetector(): Promise<Detector> {
  const native = (window as unknown as { BarcodeDetector?: { new (o: object): Detector; getSupportedFormats(): Promise<string[]> } }).BarcodeDetector
  if (native) {
    const supported = await native.getSupportedFormats()
    if (supported.includes('ean_13')) return new native({ formats: FORMATS.filter((f) => supported.includes(f)) })
  }
  const [{ BarcodeDetector, setZXingModuleOverrides }, { default: wasmUrl }] = await Promise.all([
    import('barcode-detector/ponyfill'),
    import('zxing-wasm/reader/zxing_reader.wasm?url'),
  ])
  // load the decoder from this server, not from the internet (the shop may be offline)
  setZXingModuleOverrides({ locateFile: (path: string, prefix: string) => (path.endsWith('.wasm') ? wasmUrl : prefix + path) })
  return new BarcodeDetector({ formats: [...FORMATS] })
}

async function startCamera() {
  stream?.getTracks().forEach((track) => track.stop())
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: facing.value }, width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false,
  })
  if (stopped) return stream.getTracks().forEach((track) => track.stop())
  const track = stream.getVideoTracks()[0]
  hasTorch.value = !!(track?.getCapabilities?.() as { torch?: boolean } | undefined)?.torch
  torchOn.value = false
  video.value!.srcObject = stream
  await video.value!.play()
}

async function tick() {
  const v = video.value
  if (busy || !detector || !v || v.readyState < 2) return
  busy = true
  try {
    const w = v.videoWidth * FRAME.width
    const h = v.videoHeight * FRAME.height
    canvas.width = w
    canvas.height = h
    canvas.getContext('2d')!.drawImage(v, (v.videoWidth - w) / 2, (v.videoHeight - h) / 2, w, h, 0, 0, w, h)
    const code = (await detector.detect(canvas)).map((b) => b.rawValue.trim()).find(Boolean)
    if (!code) return
    const now = performance.now()
    const stillInView = code === lastCode && now - lastSeen < SAME_CODE_GAP_MS
    lastCode = code
    lastSeen = now
    if (stillInView) return
    const result = await props.onScan(code)
    outcome.value = result
    if (result.ok) added.value += 1
  } catch {
    // a frame the decoder could not read: try the next one
  } finally {
    busy = false
  }
}

async function toggleTorch() {
  const track = stream?.getVideoTracks()[0]
  if (!track) return
  torchOn.value = !torchOn.value
  await track.applyConstraints({ advanced: [{ torch: torchOn.value } as MediaTrackConstraintSet] }).catch(() => (torchOn.value = false))
}

async function switchCamera() {
  facing.value = facing.value === 'environment' ? 'user' : 'environment'
  await startCamera().catch((e: Error) => (error.value = e.message))
}

onMounted(async () => {
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = t('The browser allows the camera only on https or on this computer (localhost). Use a USB scanner, or the mobile app.')
    return
  }
  try {
    ;[detector] = await Promise.all([makeDetector(), startCamera()])
    timer = window.setInterval(tick, 120)
  } catch (e) {
    const name = (e as Error).name
    error.value =
      name === 'NotAllowedError'
        ? t('Camera permission was refused. Allow the camera for this site in the browser settings.')
        : name === 'NotFoundError'
          ? t('No camera found on this device.')
          : (e as Error).message
  }
})

onBeforeUnmount(() => {
  stopped = true
  clearInterval(timer)
  stream?.getTracks().forEach((track) => track.stop())
})
</script>

<template>
  <AppModal :title="t('Scan items')" width="max-w-xl" @close="emit('close')">
    <p v-if="error" class="rounded-xl bg-warn-soft px-4 py-3 text-amber-900">{{ error }}</p>
    <div v-else class="relative overflow-hidden rounded-xl bg-black">
      <video ref="video" class="aspect-video w-full object-cover" muted playsinline />
      <div
        :class="[
          'pointer-events-none absolute top-1/2 left-1/2 h-[40%] w-[70%] -translate-x-1/2 -translate-y-1/2 rounded-xl border-[3px] transition-colors',
          !outcome ? 'border-white' : outcome.ok ? 'border-ok' : 'border-price',
        ]"
      />
      <div class="absolute top-2 right-2 flex gap-2">
        <button v-if="hasTorch" :class="['rounded-full p-2 text-white', torchOn ? 'bg-amber-500' : 'bg-black/50']" :title="t('Flashlight')" @click="toggleTorch">
          <Flashlight :size="18" />
        </button>
        <button class="rounded-full bg-black/50 p-2 text-white" :title="t('Switch camera')" @click="switchCamera"><SwitchCamera :size="18" /></button>
      </div>
      <p class="absolute inset-x-0 bottom-2 text-center">
        <span class="rounded-full bg-black/55 px-3 py-1 text-sm text-white">{{ t('Hold the barcode inside the frame') }}</span>
      </p>
    </div>
    <div v-if="outcome" :class="['mt-3 flex items-center gap-2.5 rounded-xl px-4 py-3 font-semibold text-white', outcome.ok ? 'bg-ok' : 'bg-price']">
      <CheckCircle2 v-if="outcome.ok" :size="20" class="shrink-0" />
      <XCircle v-else :size="20" class="shrink-0" />
      {{ outcome.message }}
    </div>

    <template #footer>
      <button class="btn-primary w-full py-3" @click="emit('close')">{{ added ? t('Done · {n} scanned', { n: added }) : t('Done') }}</button>
    </template>
  </AppModal>
</template>
