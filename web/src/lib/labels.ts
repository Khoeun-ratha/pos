// Product labels (name, price, barcode or QR code), printed through the browser's print dialog on a label printer
// or on an A4 sheet of sticky labels.
import type { Product } from '@/api/types'
import { codeSvg, type CodeKind, labelCode } from './barcode'
import { khr, usd, usdCentsToKhr } from './money'

export type LabelSize = '50x30' | '40x30' | '58roll' | 'a4'

export const LABEL_SIZES: { value: LabelSize; label: string }[] = [
  { value: '50x30', label: 'Label printer 50 × 30 mm' },
  { value: '40x30', label: 'Label printer 40 × 30 mm' },
  { value: '58roll', label: 'Receipt printer 58 mm roll' },
  { value: 'a4', label: 'A4 sheet, 3 × 8 stickers (70 × 37 mm)' },
]

/** Width × height of one label in mm. */
const DIMENSIONS: Record<LabelSize, [number, number]> = { '50x30': [50, 30], '40x30': [40, 30], '58roll': [58, 32], a4: [70, 37] }

export interface LabelOptions {
  kind: CodeKind
  size: LabelSize
  showPrice: boolean
  exchangeRate: number
  storeName: string
}

const escape = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

/** Styles for labels, shared by the on-screen preview and the printout. Sizes are in mm, as printed. */
export function labelCss(size: LabelSize) {
  const [w, h] = DIMENSIONS[size]
  return `
    .pos-label { box-sizing: border-box; width: ${w}mm; height: ${h}mm; padding: 1.5mm 2mm; overflow: hidden; background: #fff; color: #000;
      font-family: Arial, "Noto Sans Khmer", sans-serif; display: flex; flex-direction: column; gap: .6mm; }
    .pos-label .store { font-size: 1.9mm; text-transform: uppercase; letter-spacing: .1mm; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .pos-label .name { font-size: 2.9mm; font-weight: 700; line-height: 1.15; max-height: 6.7mm; overflow: hidden; }
    .pos-label .price { font-size: 4.6mm; font-weight: 800; line-height: 1; }
    .pos-label .price small { font-size: 2.4mm; font-weight: 600; margin-left: 1mm; }
    .pos-label .code { flex: 1; min-height: 0; display: flex; }
    .pos-label .code svg { width: 100%; height: 100%; }
    .pos-label .digits { font-family: "OCR B", Consolas, monospace; font-size: 2.3mm; line-height: 1; text-align: center; letter-spacing: .25mm; }
    .pos-label.qr { flex-direction: row; align-items: stretch; }
    .pos-label.qr .text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: .6mm; }
    .pos-label.qr .code { flex: none; aspect-ratio: 1; height: 100%; }
    .pos-label.qr .price small { display: block; margin: .6mm 0 0; }
    .pos-label.qr .digits { font-size: 2.1mm; margin-top: auto; text-align: left; letter-spacing: 0; overflow-wrap: anywhere; }`
}

/** One label as HTML. `svg` is the code picture from codeSvg. */
export function labelHtml(p: Product, svg: string, o: LabelOptions) {
  const price = o.showPrice ? `<div class="price">${usd(p.price)}<small>${khr(usdCentsToKhr(p.price, o.exchangeRate))}</small></div>` : ''
  const store = o.storeName ? `<div class="store">${escape(o.storeName)}</div>` : ''
  const name = `<div class="name">${escape(p.name)}</div>`
  if (o.kind === 'qr') {
    return `<div class="pos-label qr"><div class="code">${svg}</div><div class="text">${store}${name}${price}<div class="digits">${escape(labelCode(p))}</div></div></div>`
  }
  return `<div class="pos-label">${store}${name}${price}<div class="code">${svg}</div><div class="digits">${escape(labelCode(p))}</div></div>`
}

/** Prints `copies` labels of each product (products without a barcode or SKU are left out). */
export async function printLabels(products: Product[], copies: number, o: LabelOptions) {
  const labels: string[] = []
  for (const p of products) {
    const code = labelCode(p)
    if (!code) continue
    const html = labelHtml(p, await codeSvg(code, o.kind), o)
    for (let i = 0; i < copies; i++) labels.push(html)
  }
  if (!labels.length) return 0

  const [w, h] = DIMENSIONS[o.size]
  const page =
    o.size === 'a4'
      ? `@page { size: A4; margin: 0; } body { display: grid; grid-template-columns: repeat(3, ${w}mm); grid-auto-rows: ${h}mm; padding: 0 0 0 ${(210 - 3 * w) / 2}mm; }
         .pos-label { break-inside: avoid; } .pos-label:nth-child(24n) { break-after: page; }`
      : `@page { size: ${w}mm ${h}mm; margin: 0; } .pos-label { break-after: page; }`

  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;width:0;height:0;border:0'
  document.body.appendChild(frame)
  const doc = frame.contentDocument!
  doc.open()
  doc.write(`<!doctype html><html><head><title>Labels</title><style>
    body { margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    ${labelCss(o.size)}
    ${page}
  </style></head><body>${labels.join('')}</body></html>`)
  doc.close()
  frame.contentWindow!.focus()
  frame.contentWindow!.print()
  setTimeout(() => frame.remove(), 1000)
  return labels.length
}
