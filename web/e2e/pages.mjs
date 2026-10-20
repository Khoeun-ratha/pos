// Every page at desktop and phone width: no script errors, no failed requests, no sideways page scroll, and nothing
// cut off inside a card (a table wider than its card has to scroll there, which hides its last columns).
// Needs the service and the web app running. Run: node e2e/pages.mjs   (SHOTS_DIR=... saves screenshots)
import puppeteer from 'puppeteer-core'

const BASE = process.env.POS_WEB_URL ?? 'http://localhost:8080'
const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOTS = process.env.SHOTS_DIR

const PAGES = [
  'dashboard', 'sell', 'sales', 'shift', 'customers', 'products', 'labels', 'inventory', 'inventory/low',
  'inventory/movements', 'inventory/transfers', 'inventory/locations', 'suppliers', 'expenses', 'reports',
  'reports/products', 'reports/categories', 'reports/time', 'reports/payments', 'reports/cashiers', 'reports/refunds',
  'reports/discounts', 'reports/shifts', 'reports/stock', 'reports/expenses', 'reports/customers',
  'settings', 'users', 'permissions', 'activity',
]
const SIZES = { desktop: { width: 1440, height: 900 }, laptop: { width: 1280, height: 800 }, phone: { width: 390, height: 844, isMobile: true, hasTouch: true } }

const login = await (await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'admin', password: 'admin123' }) })).json()
const settings = await (await fetch(`${BASE}/api/settings`, { headers: { Authorization: `Bearer ${login.access_token}` } })).json()

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true })
const problems = []
try {
  for (const [size, viewport] of Object.entries(SIZES)) {
    const page = await browser.newPage()
    await page.setViewport(viewport)
    let current = ''
    page.on('pageerror', (e) => problems.push(`${size} /${current}: ${e.message}`))
    page.on('console', (m) => m.type() === 'error' && !m.text().includes('favicon') && problems.push(`${size} /${current}: ${m.text()}`))
    page.on('response', (r) => r.url().includes('/api/') && r.status() >= 400 && problems.push(`${size} /${current}: ${r.status()} ${r.url().replace(BASE, '')}`))
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
    await page.evaluate((l, s) => {
      localStorage.clear()
      localStorage.setItem('pos.token', l.access_token)
      localStorage.setItem('pos.user', JSON.stringify(l.user))
      localStorage.setItem('pos.settings', JSON.stringify(s))
    }, login, settings)
    for (const path of PAGES) {
      current = path
      await page.goto(`${BASE}/${path}`, { waitUntil: 'networkidle0' })
      await new Promise((r) => setTimeout(r, 300))
      const issues = await page.evaluate(() => {
        const out = []
        const doc = document.documentElement
        if (doc.scrollWidth > doc.clientWidth + 1) out.push(`page scrolls sideways (${doc.scrollWidth} > ${doc.clientWidth})`)
        // a scroll box (table card) whose content is wider than itself on a big screen hides columns
        if (innerWidth >= 1024) {
          for (const el of document.querySelectorAll('main *')) {
            const style = getComputedStyle(el)
            if (!['auto', 'scroll'].includes(style.overflowX) || el.clientWidth === 0) continue
            const first = el.querySelector('table tbody td')
            const pinned = first && getComputedStyle(first).position === 'sticky' // wide report: the name column stays
            if (el.scrollWidth > el.clientWidth + 2 && el.querySelector('table') && !pinned) {
              out.push(`table cut off: needs ${el.scrollWidth}px, has ${el.clientWidth}px (${el.querySelector('h2,h3')?.textContent?.trim() ?? el.className})`)
            }
          }
        }
        return out
      })
      for (const i of issues) problems.push(`${size} /${path}: ${i}`)
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/page-${size}-${path.replace(/\//g, '_')}.png` })
    }
    await page.close()
    console.log(`✓ ${PAGES.length} pages at ${size} width`)
  }
} finally {
  await browser.close()
}
if (problems.length) {
  console.log(`\n${problems.length} problem(s):`)
  for (const p of problems) console.log(`  - ${p}`)
  process.exit(1)
}
console.log('\nAll pages fine.')
