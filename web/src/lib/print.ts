/** Prints plain receipt text on an 80mm receipt printer (or any printer) through the browser's print dialog,
 *  with the shop logo on top (the RATHA MART mark when no logo was uploaded).
 *
 *  The text keeps its monospace columns; on paper the heading is centred, the store name and the TOTAL stand out,
 *  and the dashed rules become lines. On A4 (or Print to PDF) the receipt is a centred column, logo above it.
 *  The receipt screen shows the same paper (receiptPaper), so what you see is what prints. */
export function printReceipt(text: string, title = 'Receipt', logoUrl = '') {
  const frame = document.createElement('iframe')
  frame.style.position = 'fixed'
  frame.style.width = '0'
  frame.style.height = '0'
  frame.style.border = '0'
  document.body.appendChild(frame)

  const doc = frame.contentDocument!
  doc.open()
  doc.write(`<!doctype html><html><head><title></title><style>
    @page { size: 80mm auto; margin: 3mm; }
    body { margin: 0; }
  </style></head><body></body></html>`)
  doc.close()
  doc.title = title

  const print = () => {
    frame.contentWindow!.focus()
    frame.contentWindow!.print()
    setTimeout(() => frame.remove(), 1000)
  }
  doc.body.append(receiptPaper(doc, text, logoUrl, print)) // prints once the logo is in (or failed to load)
}

const CSS = `
  .rcpt { width: 74mm; max-width: 100%; margin: 0 auto; background: #fff; color: #000;
          font: 12px/1.35 "Cascadia Mono", Consolas, "Courier New", monospace; text-align: left; }
  .rcpt img { display: block; margin: 0 auto 2mm; max-width: 40mm; max-height: 22mm; }
  .rcpt img.brand { width: 40mm; max-width: 40mm; max-height: none; }
  .rcpt .line { white-space: pre-wrap; overflow-wrap: anywhere; }
  .rcpt .center { text-align: center; white-space: pre-wrap; }
  .rcpt .store { font-size: 17px; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 1px; }
  .rcpt .strong { font-weight: 700; }
  .rcpt .row { display: flex; justify-content: space-between; gap: 2mm; }
  .rcpt .row > :first-child { white-space: pre; overflow: hidden; text-overflow: ellipsis; }
  .rcpt .row > :last-child { white-space: nowrap; }
  .rcpt .total { font-size: 16px; font-weight: 700; margin: 1mm 0; }
  .rcpt hr { border: 0; border-top: 1px dashed #000; margin: 1.5mm 0; }
`

/** The receipt as a sheet of paper: logo, then the text laid out. `onReady` runs once the logo has loaded or
 *  failed (a missing logo is left out rather than stopping the print). */
export function receiptPaper(doc: Document, text: string, logoUrl = '', onReady?: () => void): HTMLElement {
  const paper = doc.createElement('div')
  paper.className = 'rcpt'
  const style = doc.createElement('style')
  style.textContent = CSS
  const img = doc.createElement('img')
  if (!logoUrl) img.className = 'brand'
  img.alt = ''
  img.onload = () => onReady?.()
  img.onerror = () => {
    img.remove()
    onReady?.()
  }
  img.src = new URL(logoUrl || '/receipt-logo.png', location.origin).href
  paper.append(style, img, ...layout(doc, text, !logoUrl))
  return paper
}

// "Subtotal        $50.80", "  5 x $1.60       $8.00" (not "Date:    2026-10-21")
const RULE = /^-{10,}$/
const ROW = /^(\s*\S.*?[^:\s])\s{2,}(\S.*)$/

/** One element per line of the receipt text (built with textContent, so names in it are never read as HTML).
 *  Under the RATHA MART logo (`brandLogo`), the store name line is left out: the logo already says it. */
function layout(doc: Document, text: string, brandLogo = false): HTMLElement[] {
  const lines = text.replace(/\n+$/, '').split('\n')
  const firstRule = lines.findIndex((l) => RULE.test(l))
  let storeDone = false
  let totalDone = false

  const el = (tag: string, className: string, content = '') => {
    const node = doc.createElement(tag)
    node.className = className
    node.textContent = content
    return node
  }

  return lines.map((line, i) => {
    if (RULE.test(line)) return doc.createElement('hr')
    const trimmed = line.trim()

    // the heading: store name, address, document title, number and date
    if (firstRule < 0 || i < firstRule) {
      const isMarker = trimmed.startsWith('***') // *** REPRINT / COPY ***
      if (!storeDone && trimmed && !isMarker) {
        storeDone = true
        if (brandLogo && /^ratha mart$/i.test(trimmed)) return el('div', 'center', '')
        return el('div', 'center store', trimmed)
      }
      const caps = /[A-Z]/.test(trimmed) && !/[a-z]/.test(trimmed)
      return el('div', caps ? 'center strong' : 'center', trimmed || ' ')
    }

    // a line the text centred with spaces (exchange rate, thank-you note)
    if (/^ {3,}\S/.test(line) && !/\S {2,}\S/.test(trimmed)) return el('div', 'center', trimmed)

    // "label     value" rows; the money that matters is bold
    const row = ROW.exec(line)
    if (row) {
      const [, label, value] = row
      let className = 'row'
      if (label === 'TOTAL' && !totalDone) {
        totalDone = true
        className += ' total'
      } else if (/^(TOTAL|Change|REFUNDED)\b/.test(label)) className += ' strong'
      const node = el('div', className)
      node.append(el('span', '', label), el('span', '', value))
      return node
    }
    return el('div', 'line', line || ' ')
  })
}
