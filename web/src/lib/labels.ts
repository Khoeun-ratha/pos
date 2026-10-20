// Product labels (name, price, barcode or QR code), printed through the browser's print dialog on a label printer
// (one label per page) or many on a sheet of paper, in the rows and columns the user picks.
import type { Product } from '@/api/types'
import { codeSvg, type CodeKind, labelCode } from './barcode'
import { khr, usd, usdCentsToKhr } from './money'

export type LabelSize = 'a4' | '50x30' | '40x30' | '58roll'

export const LABEL_SIZES: { value: LabelSize; label: string }[] = [
  { value: 'a4', label: 'A4 paper: rows × columns' },
  { value: '50x30', label: 'Label printer 50 × 30 mm (one per page)' },
  { value: '40x30', label: 'Label printer 40 × 30 mm (one per page)' },
  { value: '58roll', label: 'Receipt printer 58 mm roll (one per page)' },
]

/** Common sticker sheets and handy layouts for A4, as [columns, rows]. */
export const SHEET_PRESETS: [number, number][] = [
  [2, 5],
  [3, 7],
  [3, 8],
  [4, 10],
  [5, 13],
]
export const MAX_COLS = 6
export const MAX_ROWS = 20

/** A4 in mm, and the blank border kept around the labels (most printers cannot print to the edge). */
const SHEET = { width: 210, height: 297, margin: 6 }

/** Width × height of one label in mm on a label printer. */
const ROLL: Record<Exclude<LabelSize, 'a4'>, [number, number]> = { '50x30': [50, 30], '40x30': [40, 30], '58roll': [58, 32] }

export interface LabelOptions {
  kind: CodeKind
  size: LabelSize
  showPrice: boolean
  exchangeRate: number
  storeName: string
  /** A4 only: labels across and down the page. */
  cols: number
  rows: number
  /** A4 only: empty places at the start of the first page, to reuse a sticker sheet that is partly used. */
  skip: number
  /** A4 only: dashed lines to cut along with scissors. */
  cutLines: boolean
}

const escape = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

export const isSheet = (o: Pick<LabelOptions, 'size'>) => o.size === 'a4'
export const perPage = (o: Pick<LabelOptions, 'cols' | 'rows'>) => o.cols * o.rows

/** Width × height of one label in mm. On A4 the page is shared out evenly between the rows and columns. */
export function labelDims(o: Pick<LabelOptions, 'size' | 'cols' | 'rows'>): [number, number] {
  if (o.size !== 'a4') return ROLL[o.size]
  const round = (n: number) => Math.floor(n * 10) / 10
  return [round((SHEET.width - 2 * SHEET.margin) / o.cols), round((SHEET.height - 2 * SHEET.margin) / o.rows)]
}

/** Styles for labels, shared by the on-screen preview and the printout. Sizes are in mm, as printed; the text
 *  grows or shrinks with the label so small labels on a crowded sheet still fit. */
export function labelCss([w, h]: [number, number]) {
  const k = Math.min(1.5, Math.max(0.6, Math.min(h / 30, w / 45)))
  const mm = (n: number) => `${(n * k).toFixed(2)}mm`
  return `
    .pos-label { box-sizing: border-box; width: ${w}mm; height: ${h}mm; padding: ${mm(1.5)} ${mm(2)}; overflow: hidden; background: #fff; color: #000;
      font-family: Arial, "Noto Sans Khmer", sans-serif; display: flex; flex-direction: column; gap: ${mm(0.6)}; }
    .pos-label .store { font-size: ${mm(1.9)}; text-transform: uppercase; letter-spacing: .1mm; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .pos-label .name { font-size: ${mm(2.9)}; font-weight: 700; line-height: 1.15; max-height: ${mm(6.7)}; overflow: hidden; }
    .pos-label .price { font-size: ${mm(4.6)}; font-weight: 800; line-height: 1; white-space: nowrap; }
    .pos-label .price small { font-size: ${mm(2.4)}; font-weight: 600; margin-left: 1mm; }
    .pos-label .code { flex: 1; min-height: 0; display: flex; }
    .pos-label .code svg { width: 100%; height: 100%; }
    .pos-label .digits { font-family: "OCR B", Consolas, monospace; font-size: ${mm(2.3)}; line-height: 1; text-align: center; letter-spacing: .25mm; }
    .pos-label.qr { flex-direction: row; align-items: stretch; }
    .pos-label.qr .text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: ${mm(0.6)}; }
    .pos-label.qr .code { flex: none; aspect-ratio: 1; height: 100%; }
    .pos-label.qr .price small { display: block; margin: ${mm(0.6)} 0 0; }
    .pos-label.qr .digits { font-size: ${mm(2.1)}; margin-top: auto; text-align: left; letter-spacing: 0; overflow-wrap: anywhere; }
    ${
      // narrow label (many columns): QR code on top, text under it
      w < h * 1.5
        ? `.pos-label.qr { flex-direction: column; align-items: center; text-align: center; }
           .pos-label.qr .code { flex: 1; height: auto; min-height: 0; }
           .pos-label.qr .text { flex: none; width: 100%; }
           .pos-label.qr .digits, .pos-label.qr .price small { display: none; }`
        : ''
    }`
}

/** Styles for the A4 pages: a grid of rows × columns, one page after another. */
export function sheetCss(o: Pick<LabelOptions, 'size' | 'cols' | 'rows' | 'cutLines'>) {
  const [w, h] = labelDims(o)
  return `
    .pos-sheet { box-sizing: border-box; width: ${SHEET.width}mm; height: ${SHEET.height}mm; padding: ${SHEET.margin}mm; background: #fff;
      display: grid; grid-template-columns: repeat(${o.cols}, ${w}mm); grid-template-rows: repeat(${o.rows}, ${h}mm); align-content: start; }
    .pos-sheet > div { width: ${w}mm; height: ${h}mm; }
    ${o.cutLines ? '.pos-sheet .pos-label { outline: .2mm dashed #aaa; outline-offset: -.1mm; }' : ''}`
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

/** `copies` labels of each product, in order (products without a barcode or SKU are left out). Stops at `limit`. */
export async function buildLabels(products: Product[], copies: number, o: LabelOptions, limit = Infinity) {
  const labels: string[] = []
  for (const p of products) {
    if (labels.length >= limit) break
    const code = labelCode(p)
    if (!code) continue
    const html = labelHtml(p, await codeSvg(code, o.kind), o)
    for (let i = 0; i < copies && labels.length < limit; i++) labels.push(html)
  }
  return labels
}

/** Shares labels out over A4 pages, leaving the first `skip` places of page one empty. */
export function sheetPages(labels: string[], o: Pick<LabelOptions, 'cols' | 'rows' | 'skip'>) {
  const cells = [...Array<string>(Math.min(o.skip, perPage(o) - 1)).fill('<div></div>'), ...labels]
  const pages: string[] = []
  for (let i = 0; i < cells.length; i += perPage(o)) pages.push(`<div class="pos-sheet">${cells.slice(i, i + perPage(o)).join('')}</div>`)
  return pages
}

/** How many A4 pages `count` labels take. */
export const pageCount = (count: number, o: Pick<LabelOptions, 'cols' | 'rows' | 'skip'>) =>
  Math.ceil((count + Math.min(o.skip, perPage(o) - 1)) / perPage(o))

/** Prints `copies` labels of each product (products without a barcode or SKU are left out). */
export async function printLabels(products: Product[], copies: number, o: LabelOptions) {
  const labels = await buildLabels(products, copies, o)
  if (!labels.length) return 0

  const [w, h] = labelDims(o)
  const body = isSheet(o) ? sheetPages(labels, o).join('') : labels.join('')
  const page = isSheet(o)
    ? `@page { size: A4; margin: 0; } ${sheetCss(o)} .pos-sheet { break-after: page; } .pos-sheet:last-child { break-after: auto; }`
    : `@page { size: ${w}mm ${h}mm; margin: 0; } .pos-label { break-after: page; }`

  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;width:0;height:0;border:0'
  document.body.appendChild(frame)
  const doc = frame.contentDocument!
  doc.open()
  doc.write(`<!doctype html><html><head><title>Labels</title><style>
    body { margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    ${labelCss([w, h])}
    ${page}
  </style></head><body>${body}</body></html>`)
  doc.close()
  frame.contentWindow!.focus()
  frame.contentWindow!.print()
  setTimeout(() => frame.remove(), 1000)
  return labels.length
}
