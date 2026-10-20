// End-to-end check of barcode scanning in a real browser: USB scanner (also with the Khmer keyboard layout and
// with a product card focused), "3*" quantities, typed search, unknown barcodes, and the camera (Chrome's fake
// camera shows a drawn Coca-Cola barcode). Needs the service and the web app running. Run: npm run e2e
import { writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import puppeteer from 'puppeteer-core'

const BASE = process.env.POS_WEB_URL ?? 'http://localhost:8080'
const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const COKE = '8850999320014' // demo data
const RED_BULL = '8850228000016'

/** A y4m video (what Chrome's fake camera plays) of an EAN-13 barcode. */
function barcodeVideo(code) {
  const L = ['0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011']
  const R = L.map((c) => [...c].map((b) => (b === '0' ? '1' : '0')).join(''))
  const G = R.map((c) => [...c].reverse().join(''))
  const PARITY = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL']
  const d = [...code].map(Number)
  let bits = '101'
  d.slice(1, 7).forEach((digit, i) => (bits += (PARITY[d[0]][i] === 'L' ? L : G)[digit]))
  bits += '01010'
  d.slice(7).forEach((digit) => (bits += R[digit]))
  bits += '101'

  const W = 640, H = 480, module = 3
  const y = Buffer.alloc(W * H, 255)
  const x0 = Math.floor((W - bits.length * module) / 2)
  for (let row = 170; row < 310; row++) {
    for (let i = 0; i < bits.length; i++) if (bits[i] === '1') y.fill(0, row * W + x0 + i * module, row * W + x0 + (i + 1) * module)
  }
  const uv = Buffer.alloc((W / 2) * (H / 2), 128)
  const frame = Buffer.concat([Buffer.from('FRAME\n'), y, uv, uv])
  const file = join(tmpdir(), 'pos-e2e-barcode.y4m')
  writeFileSync(file, Buffer.concat([Buffer.from(`YUV4MPEG2 W${W} H${H} F10:1 Ip A1:1 C420jpeg\n`), ...Array(20).fill(frame)]))
  return file
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  defaultViewport: { width: 1440, height: 900 },
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${barcodeVideo(COKE)}`],
})
const page = (await browser.pages())[0]
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
// the unknown-barcode check asks the service on purpose and gets "not found"
page.on('console', (m) => m.type() === 'error' && !m.text().includes('404') && !m.text().includes('favicon') && errors.push(m.text()))

const step = (name) => console.log(`✓ ${name}`)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const cart = () => page.$$eval('#cart li', (els) => els.map((el) => el.textContent.replace(/\s+/g, ' ').trim()))
const qty = async (name) => {
  const line = (await cart()).find((l) => l.includes(name))
  return line ? Number(/\$[\d.]+ (\d+)\$/.exec(line)?.[1] ?? NaN) : 0
}
const expectQty = async (name, n, what) => {
  const got = await qty(name)
  if (got !== n) throw new Error(`${what}: expected ${n} × ${name}, cart is ${JSON.stringify(await cart())}`)
  step(what)
}
/** A USB scanner: the keys come a few ms apart, then Enter. */
const scan = async (code) => {
  await page.keyboard.type(code, { delay: 4 })
  await page.keyboard.press('Enter')
  await sleep(400)
}

async function signIn(username, password) {
  const login = await (await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })).json()
  const settings = await (await fetch(`${BASE}/api/settings`, { headers: { Authorization: `Bearer ${login.access_token}` } })).json()
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
  await page.evaluate((l, s) => {
    localStorage.clear()
    localStorage.setItem('pos.token', l.access_token)
    localStorage.setItem('pos.user', JSON.stringify(l.user))
    localStorage.setItem('pos.settings', JSON.stringify(s))
    localStorage.setItem('pos.sound', 'off')
  }, login, settings)
  await page.goto(`${BASE}/sell`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('#cart')
}

try {
  await signIn('manager', 'manager123')

  // a product card has the focus: the scanner's Enter must not also "press" that card
  await (await page.$$('section button.group'))[5].focus()
  await scan(COKE)
  if ((await cart()).length !== 1) throw new Error(`scan with a card focused: ${JSON.stringify(await cart())}`)
  await expectQty('Coca-Cola', 1, 'USB scan adds the item (a focused product card is not pressed)')
  if (!(await page.$eval('#cart li', (el) => el.classList.contains('line-flash')))) throw new Error('added line does not flash')
  step('added line flashes')

  // Khmer keyboard layout: Khmer digits arrive, but the physical keys are the barcode's
  await page.evaluate(async (code) => {
    document.activeElement?.blur()
    for (const d of code) {
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: '០១២៣៤៥៦៧៨៩'[Number(d)], code: `Digit${d}`, bubbles: true }))
      await new Promise((r) => setTimeout(r, 3))
    }
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }))
  }, COKE)
  await sleep(400)
  await expectQty('Coca-Cola', 2, 'scan with the Khmer keyboard layout')

  // "3*" typed by a person, then a scan into the same box
  await page.focus('input[placeholder*="F2"]')
  await page.keyboard.type('3*', { delay: 120 })
  await page.waitForFunction(() => document.body.innerText.includes('Next scan or tap adds 3'))
  await sleep(150)
  await scan(RED_BULL)
  await expectQty('Red Bull', 3, '"3*" then a scan adds 3')
  if ((await page.$eval('input[placeholder*="F2"]', (el) => el.value)) !== '') throw new Error('search box not cleared after the scan')

  // a person typing a name and Enter still searches
  await page.keyboard.type('sprite', { delay: 90 })
  await page.keyboard.press('Enter')
  await sleep(300)
  await expectQty('Sprite', 1, 'typed name + Enter adds the only match')

  // camera (tablets / phones): adds once while the barcode stays in view
  await page.click('button[aria-label="Scan with camera"]')
  await page.waitForFunction(() => document.querySelector('[data-modal]')?.innerText.includes('Coca-Cola'), { timeout: 20000 })
  await sleep(3000)
  const camera = await page.$eval('[data-modal]', (el) => el.innerText)
  if (!camera.includes('Done · 1 scanned')) throw new Error(`camera added the same item more than once: ${camera}`)
  await page.evaluate(() => [...document.querySelectorAll('[data-modal] button')].find((b) => b.textContent.includes('Done')).click())
  await sleep(300)
  await expectQty('Coca-Cola', 3, 'camera scan adds the item once')
  if (await page.$('video')) throw new Error('camera still on after Done')

  // unknown barcode: a manager can create the product with the barcode filled in
  await scan('1234567890999')
  await page.waitForFunction(() => document.body.innerText.includes('Add it as a new product?'), { timeout: 4000 })
  await (await page.waitForFunction(() => [...document.querySelectorAll('[data-modal] button')].find((b) => b.textContent.includes('New product')))).asElement().click()
  await page.waitForFunction(() => location.pathname === '/products')
  await page.waitForFunction(() => [...document.querySelectorAll('[data-modal] input')].some((i) => i.value === '1234567890999'), { timeout: 4000 })
  step('unknown barcode opens a new product with the barcode filled in')

  if (errors.length) throw new Error(`page errors: ${errors.join(' | ')}`)
  console.log('\nScanner checks passed.')
} catch (e) {
  console.error(`✗ ${e.message}`)
  process.exitCode = 1
} finally {
  await browser.close()
}
