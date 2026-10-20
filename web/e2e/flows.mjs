// The till's other everyday flows in a real browser, checked against the service after each step:
// open a shift with dollars and riel, discount with a manager PIN, hold and resume, split card + cash,
// cash out, and close the shift counting dollars and riel (balanced).
// Needs the service and the web app running. Run: node e2e/flows.mjs
import puppeteer from 'puppeteer-core'

const BASE = process.env.POS_WEB_URL ?? 'http://localhost:8080'
const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const SHOTS = process.env.SHOTS_DIR

const signIn = async (username, password) =>
  (await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })).json()
const caller = (token) => async (path, body, method = body ? 'POST' : 'GET') => {
  const r = await fetch(`${BASE}/api${path}`, { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: body && JSON.stringify(body) })
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`)
  return r.status === 204 ? null : r.json()
}

// a cashier of its own, so the real staff's drawers are never touched; deactivated again at the end
const admin = caller((await signIn('admin', 'admin123')).access_token)
const TESTER = { username: 'e2e_flow', full_name: 'E2E test cashier', password: 'e2eflow123', pin: '9876' }
const existing = (await admin('/users')).find((u) => u.username === TESTER.username)
const tester = existing
  ? await admin(`/users/${existing.id}`, { password: TESTER.password, pin: TESTER.pin, is_active: true }, 'PATCH')
  : await admin('/users', { ...TESTER, role: 'cashier' })
const login = await signIn(TESTER.username, TESTER.password)
const api = caller(login.access_token)
const settings = await api('/settings')
const rate = settings.exchange_rate

// start from a closed drawer
const left = await api('/shifts/current')
if (left) await api('/shifts/current/close', { counted_usd: left.expected_cash })

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, defaultViewport: { width: 1440, height: 900 } })
const page = (await browser.pages())[0]
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => m.type() === 'error' && !m.text().includes('favicon') && !m.text().includes('status of 4') && errors.push(m.text()))

const step = (name) => console.log(`✓ ${name}`)
const shot = (name) => SHOTS && page.screenshot({ path: `${SHOTS}/flow-${name}.png` })
const expect = (ok, what) => { if (!ok) throw new Error(what) }
const clickText = async (selector, text) => {
  const handle = await page.waitForFunction(
    (sel, t) => [...document.querySelectorAll(sel)].find((el) => el.textContent.trim().includes(t) && !el.disabled && el.offsetParent),
    { timeout: 8000 }, selector, text,
  )
  await handle.asElement().click()
}
const answerDialog = async (text, button) => {
  await page.waitForSelector('#dialog-input', { visible: true })
  await page.type('#dialog-input', text)
  await clickText('button', button)
  // closed, or already the next question (cash out asks the amount, then the reason, in the same dialog)
  await page.waitForFunction(() => !document.querySelector('#dialog-input')?.value)
}
const cartText = () => page.$eval('#cart', (el) => el.textContent.replace(/\s+/g, ' '))
const grandTotal = async () => (await cartText()).match(/Grand Total\s*\$(\d+\.\d\d)/)[1]

try {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
  await page.evaluate((l, s) => {
    localStorage.clear()
    localStorage.setItem('pos.token', l.access_token)
    localStorage.setItem('pos.user', JSON.stringify(l.user))
    localStorage.setItem('pos.settings', JSON.stringify(s))
  }, login, settings)

  // 1. open the shift with $10 and 41,000 riel
  await page.goto(`${BASE}/shift`, { waitUntil: 'networkidle0' })
  const inputs = await page.$$('input[inputmode]')
  await inputs[0].click({ count: 3 })
  await inputs[0].type('10')
  await inputs[1].type(String(10 * rate))
  await page.waitForFunction(() => document.body.textContent.includes('Opening cash: $20.00'))
  await clickText('button', 'Open shift')
  await page.waitForFunction(() => document.querySelector('header a[href="/shift"]').textContent.includes('Shift open'))
  const opened = await api('/shifts/current')
  expect(opened.opening_cash === 2000, `opening cash ${opened.opening_cash}, expected 2000`)
  step('shift opened with $10 + 10 dollars in riel = $20.00')

  // 2. four cokes, 10% off the order: the cashier needs the manager PIN
  await page.goto(`${BASE}/sell`, { waitUntil: 'networkidle0' })
  await page.waitForFunction(() => document.querySelectorAll('section button.group').length > 10)
  for (let i = 0; i < 4; i++) await clickText('section button.group', 'Coca-Cola 330ml')
  await page.waitForFunction(() => /Coca-Cola 330ml.*\$3\.00/.test(document.querySelector('#cart').textContent))
  await clickText('#cart button', '%')
  await page.type('#cart input[placeholder="0.00"]', '10')
  await page.keyboard.press('Enter')
  await answerDialog('2222', 'Approve')
  await page.waitForFunction(() => document.querySelector('#cart').textContent.includes('-$0.30'))
  expect(await grandTotal() === '2.97', `total ${await grandTotal()}, expected 2.97 (3.00 - 10% + 10% VAT)`)
  step('10% discount approved with manager PIN, total $2.97')
  await shot('discount')

  // 3. hold it, then resume it
  await page.click('#cart button[title^="Hold this sale"]')
  await answerDialog('Flow test', 'OK')
  await page.waitForFunction(() => document.querySelector('#cart').textContent.includes('Tap a product to add'))
  expect((await api('/parked')).some((o) => o.label === 'Flow test' && o.total === 297), 'held order not on the service')
  await clickText('#cart button', 'Flow test')
  await page.waitForFunction(() => document.querySelector('#cart').textContent.includes('-$0.30'))
  expect(!(await api('/parked')).some((o) => o.label === 'Flow test'), 'resumed order still held')
  step('held and resumed with its discount')

  // 4. pay $1.00 by card and the rest in cash (exact); the discount is approved again after the hold
  await clickText('#cart button', 'Pay ·')
  if (await page.$('#dialog-input')) await answerDialog('2222', 'Approve')
  await page.waitForSelector('input[placeholder^="Amount received"]')
  await clickText('button', 'Card')
  await page.type('input[placeholder^="Amount received"]', '1')
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => document.body.textContent.includes('Still due'))
  await clickText('button', 'Cash')
  await clickText('button', 'Exact')
  await shot('split')
  await clickText('button', 'Complete sale')
  await page.waitForFunction(() => document.body.textContent.includes('Sale complete'))
  await page.waitForFunction(() => /Receipt:\s+\d{8}-\d{4}/.test(document.querySelector('pre')?.textContent ?? ''))
  const receipt = await page.$eval('pre', (el) => el.textContent)
  expect(/Card USD\s+\$1\.00/.test(receipt) && /Discount/i.test(receipt), `receipt is missing the card or discount:\n${receipt}`)
  await clickText('button', 'New sale')
  const afterSale = await api('/shifts/current')
  expect(afterSale.card_sales === 100 && afterSale.cash_sales === 197, `shift card ${afterSale.card_sales} cash ${afterSale.cash_sales}`)
  step('split $1.00 card + $1.97 cash, receipt shows both')

  // 5. cash out $2.50 for ice
  await page.goto(`${BASE}/shift`, { waitUntil: 'networkidle0' })
  await clickText('button', 'Cash out')
  await answerDialog('2.50', 'OK')
  await answerDialog('Ice', 'OK')
  await page.waitForFunction(() => document.body.textContent.includes('-$2.50'))
  const beforeClose = await api('/shifts/current')
  expect(beforeClose.expected_cash === 2000 + 197 - 250, `expected ${beforeClose.expected_cash}`)
  step('cash out $2.50, expected in drawer $19.47')

  // 6. close: count $10.47 and 36,900 riel (= $9.00), balanced
  await clickText('button', 'Close shift')
  await page.waitForSelector('input[placeholder="0.00"]')
  await page.type('input[placeholder="0.00"]', '10.47')
  await page.type('input[placeholder="0"]', String(9 * rate))
  await page.waitForFunction(() => /Counted\s*\$19\.47/.test(document.querySelector('#close-form').textContent))
  await shot('count')
  await clickText('.fixed button', 'Close shift')
  await page.waitForFunction(() => document.body.textContent.includes('Shift closed'))
  await page.waitForFunction(() => document.body.textContent.includes('Balanced'))
  expect((await api('/shifts/current')) === null, 'shift still open')
  step('closed with dollars + riel counted: balanced')
  await shot('closed')

  if (errors.length) throw new Error(`browser errors:\n${errors.join('\n')}`)
  console.log('\nFlow checks passed.')
} catch (e) {
  await shot('failure')
  console.error(`✗ ${e.message}`)
  process.exitCode = 1
} finally {
  await browser.close()
  await admin(`/users/${tester.id}`, { is_active: false }, 'PATCH')
}
