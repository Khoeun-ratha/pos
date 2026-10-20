// Draws the RATHA MART app icons for Android, iOS and the web app from one drawing (the mark of
// web/public/favicon.svg). Run from the repo:  node mobile/tool/app_icons.mjs
// Uses Chrome through the web app's puppeteer-core (cd web && npm install first).
import { mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const puppeteer = createRequire(join(ROOT, 'web', 'package.json'))('puppeteer-core')
const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const BLUE = '#1d4ed8'
const gradient = (id) =>
  `<linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="${BLUE}"/></linearGradient>`
// the bag and the R on a 64 x 64 grid; its middle is (32, 32.4)
const HANDLE = 'M22.8 26c0-7.6 4-11.8 9.2-11.8s9.2 4.2 9.2 11.8'
const BAG = 'M17.6 24h28.8a2 2 0 0 1 2 1.86l1.5 21.6A4.4 4.4 0 0 1 45.5 52h-27a4.4 4.4 0 0 1-4.4-4.54l1.5-21.6a2 2 0 0 1 2-1.86z'
const R = 'M27.5 46.5v-15h5.6a4.5 4.5 0 0 1 0 9h-5.6m5.4 0 5 6'
const bag = (rColor = BLUE, dot = true) =>
  `<path d="${HANDLE}" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/><path d="${BAG}" fill="#fff"/>` +
  `<path d="${R}" fill="none" stroke="${rColor}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>` +
  (dot ? '<circle cx="44" cy="30" r="1.9" fill="#f59e0b"/>' : '')
/** The bag centred at (cx, cy) of the canvas, `scale` times its size on the 64 grid. */
const placed = (cx, cy, scale, inner) => `<g transform="translate(${cx} ${cy}) scale(${scale}) translate(-32 -32.4)">${inner}</g>`
const svg = (box, body) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${box} ${box}"><defs>${gradient('g')}</defs>${body}</svg>`

const ART = {
  // iOS and the web: a full square (iOS rounds the corners itself and wants no transparency)
  full: svg(64, `<rect width="64" height="64" fill="url(#g)"/>${placed(32, 32, 1.05, bag())}`),
  // older Android: rounded square / circle with a little room around it
  legacy: svg(64, `<rect x="3" y="3" width="58" height="58" rx="14" fill="url(#g)"/>${placed(32, 32, 0.9, bag())}`),
  round: svg(64, `<circle cx="32" cy="32" r="29" fill="url(#g)"/>${placed(32, 32, 0.84, bag())}`),
  // Android 8+ adaptive icon (108 x 108, the launcher shows the middle 72 and may cut down to a circle of 66)
  background: svg(108, '<rect width="108" height="108" fill="url(#g)"/>'),
  foreground: svg(108, placed(54, 54, 1.12, bag())),
  // Android 13 themed icon: one colour, the R cut out of the bag
  monochrome: svg(108, `<mask id="m"><rect width="108" height="108" fill="#fff"/>${placed(54, 54, 1.12, `<path d="${R}" fill="none" stroke="#000" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>`)}</mask>` +
    `<g mask="url(#m)">${placed(54, 54, 1.12, `<path d="${HANDLE}" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/><path d="${BAG}" fill="#fff"/>`)}</g>`),
}

const RES = join(ROOT, 'mobile', 'android', 'app', 'src', 'main', 'res')
const IOS = join(ROOT, 'mobile', 'ios', 'Runner', 'Assets.xcassets', 'AppIcon.appiconset')
const ANDROID = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 }
const jobs = []
for (const [density, k] of Object.entries(ANDROID)) {
  const dir = join(RES, `mipmap-${density}`)
  jobs.push(['legacy', 48 * k, join(dir, 'ic_launcher.png')], ['round', 48 * k, join(dir, 'ic_launcher_round.png')])
  for (const layer of ['background', 'foreground', 'monochrome']) jobs.push([layer, 108 * k, join(dir, `ic_launcher_${layer}.png`)])
}
for (const [pt, scales] of [[20, [1, 2, 3]], [29, [1, 2, 3]], [40, [1, 2, 3]], [60, [2, 3]], [76, [1, 2]], [83.5, [2]], [1024, [1]]]) {
  for (const s of scales) jobs.push(['full', pt * s, join(IOS, `Icon-App-${pt}x${pt}@${s}x.png`), true])
}
const WEB = join(ROOT, 'web', 'public')
jobs.push(['full', 180, join(WEB, 'apple-touch-icon.png'), true], ['legacy', 192, join(WEB, 'icon-192.png')], ['legacy', 512, join(WEB, 'icon-512.png')])

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage()
for (const [art, size, file, opaque] of jobs) {
  await page.setViewport({ width: size, height: size })
  await page.setContent(`<style>html,body{margin:0;background:${opaque ? '#1d4ed8' : 'transparent'}}svg{display:block;width:${size}px;height:${size}px}</style>${ART[art]}`)
  mkdirSync(dirname(file), { recursive: true })
  writeFileSync(file, await page.screenshot({ omitBackground: !opaque, clip: { x: 0, y: 0, width: size, height: size } }))
}
await browser.close()

// Android 8+: the adaptive icon made of the three layers
const adaptive = `<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@mipmap/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />
</adaptive-icon>
`
mkdirSync(join(RES, 'mipmap-anydpi-v26'), { recursive: true })
writeFileSync(join(RES, 'mipmap-anydpi-v26', 'ic_launcher.xml'), adaptive)
writeFileSync(join(RES, 'mipmap-anydpi-v26', 'ic_launcher_round.xml'), adaptive)
console.log(`${jobs.length} icons drawn`)
