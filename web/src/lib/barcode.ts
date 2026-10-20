// Barcode and QR code pictures (SVG) for product labels, made in the browser with ZXing (shipped with the app,
// so it works offline), and new in-store barcodes for products that come without one.
import type { Product } from '@/api/types'

export type CodeKind = 'barcode' | 'qr'

/** The GS1 check digit of an EAN / UPC code given without it. */
export function checkDigit(digits: string): number {
  const sum = [...digits].reverse().reduce((s, d, i) => s + Number(d) * (i % 2 === 0 ? 3 : 1), 0)
  return (10 - (sum % 10)) % 10
}

const validGtin = (code: string) => /^\d+$/.test(code) && checkDigit(code.slice(0, -1)) === Number(code.at(-1))

/** EAN-13 / UPC-A / EAN-8 when the code is one (shop scanners read them best); any other text as Code 128. */
export function barcodeFormat(code: string) {
  if (code.length === 13 && validGtin(code)) return 'EAN13'
  if (code.length === 12 && validGtin(code)) return 'UPCA'
  if (code.length === 8 && validGtin(code)) return 'EAN8'
  return 'Code128'
}

/** What a label's code holds: the barcode, or the SKU when there is no barcode. */
export const labelCode = (p: Product) => p.barcode || p.sku || ''

/** A new EAN-13 starting with 200: GS1 keeps 200-299 for numbers a shop makes for itself, so it never
 *  clashes with a maker's barcode. The server refuses a number already used by another product. */
export function newStoreBarcode(): string {
  const body = `200${String(Math.floor(Math.random() * 1e9)).padStart(9, '0')}`
  return body + checkDigit(body)
}

let ready: Promise<typeof import('zxing-wasm/writer')> | null = null

function writer() {
  ready ??= Promise.all([import('zxing-wasm/writer'), import('zxing-wasm/writer/zxing_writer.wasm?url')]).then(([zxing, { default: wasmUrl }]) => {
    // load the encoder from this server, not from the internet (the shop may be offline)
    zxing.prepareZXingModule({ overrides: { locateFile: (path: string, prefix: string) => (path.endsWith('.wasm') ? wasmUrl : prefix + path) } })
    return zxing
  })
  return ready
}

/** The code as an SVG that fills its box. A barcode's bars stretch to the whole box (that keeps the bar widths in
 *  proportion, so it still scans) and the label prints the digits under it; a QR code keeps its square shape. */
export async function codeSvg(code: string, kind: CodeKind): Promise<string> {
  const { writeBarcode } = await writer()
  const format = kind === 'qr' ? 'QRCode' : barcodeFormat(code)
  const result = await writeBarcode(code, { format, withHRT: false, withQuietZones: true, options: kind === 'qr' ? 'ecLevel=M' : '' })
  if (result.error) throw new Error(result.error)
  const svg = result.svg.slice(result.svg.indexOf('<svg'))
  const width = /width="([\d.]+)"/.exec(svg)?.[1]
  const height = /height="([\d.]+)"/.exec(svg)?.[1]
  return svg.replace(/<svg width="[\d.]+" height="[\d.]+"/, `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="${kind === 'qr' ? 'xMidYMid meet' : 'none'}" shape-rendering="crispEdges"`)
}
