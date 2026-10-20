/** Prints plain receipt text on an 80mm receipt printer (or any printer) through the browser's print dialog,
 *  with the shop logo on top when there is one. */
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
    img { display: block; margin: 0 auto 2mm; max-width: 40mm; max-height: 22mm; }
    pre { font: 12px/1.35 "Cascadia Mono", Consolas, "Courier New", monospace; white-space: pre; margin: 0; }
  </style></head><body><pre></pre></body></html>`)
  doc.close()
  doc.title = title
  doc.querySelector('pre')!.textContent = text

  const print = () => {
    frame.contentWindow!.focus()
    frame.contentWindow!.print()
    setTimeout(() => frame.remove(), 1000)
  }
  if (!logoUrl) return print()
  const img = doc.createElement('img')
  img.onload = print
  img.onerror = () => {
    img.remove() // print without the logo rather than not at all
    print()
  }
  img.src = new URL(logoUrl, location.origin).href
  doc.body.prepend(img)
}
