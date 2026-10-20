// End-to-end check in a real browser: log in, sell, pay in riel, see the receipt, refund, visit every page.
// Needs the service and the web app running (start_all.bat). Run: npm run e2e
import { writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import puppeteer from 'puppeteer-core'

const BASE = process.env.POS_WEB_URL ?? 'http://localhost:8080'
const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOTS = process.env.SHOTS_DIR
const KEEP_PHOTO = process.env.KEEP_PHOTO === '1' // leave the test photo on Coca-Cola (for screenshots)

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, defaultViewport: { width: 1440, height: 900 } })
const errors = []

/** Signs in through the login form in its own window. After a weak demo password Chrome shows its
 * "found in a data breach" warning over that window, which blocks clicks and typing, so the rest of the
 * test runs in a fresh window (see signIn). */
async function checkLoginForm(username, password) {
  const context = await browser.createBrowserContext()
  const form = await context.newPage()
  await form.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
  await form.type('#username', username)
  await form.type('#secret', password)
  await form.keyboard.press('Enter')
  await form.waitForFunction(() => location.pathname === '/sell')
  await context.close()
}

/** Logs in through the service and starts the web app already signed in. */
async function signIn(username, password) {
  const login = await (await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })).json()
  const settings = await (await fetch(`${BASE}/api/settings`, { headers: { Authorization: `Bearer ${login.access_token}` } })).json()
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
  await page.evaluate((l, s) => {
    localStorage.clear()
    localStorage.setItem('pos.token', l.access_token)
    localStorage.setItem('pos.user', JSON.stringify(l.user))
    localStorage.setItem('pos.settings', JSON.stringify(s))
  }, login, settings)
  await page.goto(`${BASE}/sell`, { waitUntil: 'networkidle0' })
}

const page = (await browser.pages())[0]
page.on('pageerror', (e) => errors.push(e.message))
if (process.env.LOG_WRITES) {
  page.on('request', (r) => r.url().includes('/api/') && r.method() !== 'GET' && console.log(`    ${r.method()} ${r.url().replace(BASE, '')}`))
}
page.on('console', (m) => m.type() === 'error' && !m.text().includes('favicon') && errors.push(m.text()))

const step = (name) => console.log(`✓ ${name}`)
const shot = (name) => SHOTS && page.screenshot({ path: `${SHOTS}/e2e-${name}.png` })
const clickText = async (selector, text) => {
  const handle = await page.waitForFunction(
    (sel, t) => [...document.querySelectorAll(sel)].find((el) => el.textContent.trim().includes(t) && !el.disabled),
    { timeout: 8000 },
    selector,
    text,
  )
  await handle.asElement().click()
}
const textOf = (selector) => page.$eval(selector, (el) => el.textContent)

try {
  await checkLoginForm('cashier', 'cashier123')
  step('login form works')

  await signIn('cashier', 'cashier123')
  step('cashier signed in')

  // open a shift if needed
  await page.waitForSelector('header a[href="/shift"]')
  if ((await textOf('header a[href="/shift"]')).includes('No shift')) {
    await page.goto(`${BASE}/shift`, { waitUntil: 'networkidle0' })
    await clickText('button', 'Open shift')
    await page.waitForFunction(() => document.querySelector('header a[href="/shift"]').textContent.includes('Shift open'))
    await page.goto(`${BASE}/sell`, { waitUntil: 'networkidle0' })
    step('shift opened')
  }

  // add products: tap a card twice, scan a barcode with Enter
  await page.waitForFunction(() => document.querySelectorAll('section button.group').length > 10)
  await clickText('section button.group', 'Coca-Cola 330ml')
  await clickText('section button.group', 'Coca-Cola 330ml')
  await page.type('input[placeholder^="Search or scan"]', '8850001500017') // Jasmine Rice 5kg
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => document.querySelector('#cart').textContent.includes('Jasmine Rice'))
  const grand = await page.$eval('#cart', (el) => el.textContent.match(/Grand Total\s*\$(\d+\.\d\d)/)[1])
  if (grand !== '8.80') throw new Error(`grand total ${grand}, expected 8.80 (2 x 0.75 + 6.50 + 10% VAT)`)
  step('cart total $8.80 is correct')
  await shot('cart')

  // pay 40,000 riel cash, expect change
  await clickText('#cart button', 'Pay ·')
  await page.waitForSelector('input[placeholder^="Amount received"]')
  await clickText('button', 'KHR')
  await page.type('input[placeholder^="Amount received"]', '40000')
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => document.body.textContent.includes('Change to give'))
  await shot('payment')
  await clickText('button', 'Complete sale')
  await page.waitForFunction(() => document.body.textContent.includes('Sale complete'))
  await page.waitForFunction(() => /Receipt:\s+\d{8}-\d{4}/.test(document.querySelector('pre').textContent))
  const receiptNo = (await textOf('pre')).match(/Receipt:\s+(\d{8}-\d{4})/)[1]
  step(`sale ${receiptNo} saved, receipt shown`)
  await shot('receipt')
  await clickText('button', 'New sale')

  // refund one item: the cashier needs the manager PIN
  await page.goto(`${BASE}/sales`, { waitUntil: 'networkidle0' })
  await clickText('section button', receiptNo)
  await clickText('button', 'Refund')
  await page.waitForSelector('input[placeholder^="e.g. Damaged"]')
  const qtyInputs = await page.$$('input[type="number"]')
  for (const input of qtyInputs.slice(1)) {
    await input.click({ count: 3 })
    await input.type('0')
  }
  await page.type('input[placeholder^="e.g. Damaged"]', 'Damaged can')
  await clickText('.fixed button', 'Refund')
  await page.waitForSelector('#dialog-input')
  await page.type('#dialog-input', '2222')
  await clickText('button', 'Approve')
  // the success message, not just any "refunded" text (earlier test sales are on the same list)
  const outcome = await page.waitForFunction(() => {
    const toasts = [...document.querySelectorAll('[role="status"]')].map((t) => t.textContent.trim())
    return toasts.find((t) => t.startsWith('Refunded') || t.length > 0)
  })
  const message = await outcome.jsonValue()
  if (!message.startsWith('Refunded $1.65')) throw new Error(`refund failed: ${message}`)
  step('refund approved with manager PIN')

  // visit every page as the admin
  await signIn('admin', 'admin123')
  for (const path of ['dashboard', 'sales', 'shift', 'reports', 'products', 'suppliers', 'customers', 'settings', 'users', 'activity']) {
    await page.goto(`${BASE}/${path}`, { waitUntil: 'networkidle0' })
    await page.waitForFunction((p) => document.querySelector('header h1')?.textContent.trim().length && location.pathname === `/${p}`, {}, path)
    await shot(path)
  }
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle0' })
  await page.waitForFunction(() => document.body.textContent.includes('Net sales') && document.querySelectorAll('canvas').length >= 2)
  const overflow = await page.evaluate(() => document.querySelector('main').scrollWidth - document.querySelector('main').clientWidth)
  if (overflow > 0) throw new Error(`dashboard is ${overflow}px wider than the screen`)
  step('dashboard shows figures and charts')

  // product photo: upload in the product form, see it on the sell screen, then remove it again
  const photoPath = join(tmpdir(), 'pos-e2e-photo.png')
  const pngBase64 = await page.evaluate(() => {
    const canvas = Object.assign(document.createElement('canvas'), { width: 640, height: 480 })
    const g = canvas.getContext('2d')
    g.fillStyle = '#f8fafc'
    g.fillRect(0, 0, 640, 480)
    g.fillStyle = '#dc2626'
    g.beginPath()
    g.roundRect(250, 70, 140, 340, 30)
    g.fill()
    g.fillStyle = '#fff'
    g.font = 'bold 34px sans-serif'
    g.fillText('COLA', 278, 250)
    return canvas.toDataURL('image/png').split(',')[1]
  })
  writeFileSync(photoPath, Buffer.from(pngBase64, 'base64'))
  await page.goto(`${BASE}/products`, { waitUntil: 'networkidle0' })
  await page.type('input[placeholder^="Search name"]', 'Coca-Cola')
  await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 1)
  await clickText('tbody button[title="Edit"]', '')
  const fileInput = await page.waitForSelector('#product-form input[type="file"]')
  await fileInput.uploadFile(photoPath)
  await page.waitForFunction(() => document.querySelector('#product-form img')?.src.startsWith('blob:'))
  await shot('product-photo-form')
  await clickText('button', 'Save')
  await page.waitForFunction(() => !document.querySelector('#product-form'))
  await page.goto(`${BASE}/sell`, { waitUntil: 'networkidle0' })
  const img = await page.waitForFunction(() => {
    const card = [...document.querySelectorAll('section button.group')].find((b) => b.textContent.includes('Coca-Cola'))
    const el = card?.querySelector('img')
    return el?.complete && el.naturalWidth > 0 && el.src
  })
  const src = await img.jsonValue()
  if (!/\/uploads\/products\/\d+-[0-9a-f]+\.webp$/.test(src)) throw new Error(`unexpected photo address ${src}`)
  await shot('sell-with-photo')
  step('product photo uploaded and shown on the sell screen')

  if (!KEEP_PHOTO) {
    await page.goto(`${BASE}/products`, { waitUntil: 'networkidle0' })
    await page.type('input[placeholder^="Search name"]', 'Coca-Cola')
    await page.waitForFunction(() => document.querySelectorAll('tbody tr').length === 1)
    await clickText('tbody button[title="Edit"]', '')
    await clickText('#product-form button', 'Remove')
    await clickText('button', 'Save')
    await page.waitForFunction(() => !document.querySelector('#product-form'))
    const left = await (await fetch(`${BASE}${new URL(src).pathname}`)).status
    if (left !== 404) throw new Error(`removed photo is still served (${left})`)
    step('photo removed again (test data cleaned up)')
  }
  step('all admin pages open')

  await signIn('cashier', 'cashier123')
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle0' })
  if (!(await page.evaluate(() => location.pathname === '/sell'))) throw new Error('cashier could open the dashboard')
  step('cashier is kept out of the dashboard')

  // phone size: menu becomes a drawer, cart becomes a bottom bar
  await page.setViewport({ width: 390, height: 844 })
  await page.goto(`${BASE}/sell`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('button[aria-label="Open menu"]', { visible: true })
  await shot('phone')
  step('phone layout')

  if (errors.length) throw new Error(`browser errors:\n${errors.join('\n')}`)
  console.log('\nAll checks passed')
} catch (e) {
  await shot('failure')
  console.error(`\n✗ ${e.message}`)
  process.exitCode = 1
} finally {
  await browser.close()
}
