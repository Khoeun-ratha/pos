"""Plain-text receipts, ready for ESC/POS thermal printers (42 cols = 80mm, 32 cols = 58mm)."""

from .models import Sale
from .pricing import usd_cents_to_khr

METHOD_NAMES = {"cash": "Cash", "card": "Card", "khqr": "KHQR"}


def usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def khr(riel: int) -> str:
    return f"{riel:,} KHR"


def _row(left: str, right: str, width: int) -> str:
    space = width - len(right) - 1
    if len(left) > space:
        left = left[: max(space, 0)]
    return f"{left:<{space}} {right}"


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def render(sale: Sale, store: dict[str, str], width: int = 42, reprint: bool = False) -> str:
    rule = "-" * width
    out: list[str] = []
    if reprint:  # a copy must never pass for the original
        out.append("*** REPRINT / COPY ***".center(width).rstrip())

    out += [line.center(width).rstrip() for line in _wrap(store["store_name"], width)]
    # a branch prints its own name and address (the customer is there, not at the main shop)
    address = store.get("store_address")
    if sale.location is not None:
        out += [line.center(width).rstrip() for line in _wrap(f"{sale.location.name} branch", width)]
        address = sale.location.address
    if address:
        out += [line.center(width).rstrip() for line in _wrap(address, width)]
    if store.get("store_phone"):
        out.append(f"Tel: {store['store_phone']}".center(width).rstrip())
    out.append(rule)
    out.append(f"Receipt: {sale.receipt_no}")
    out.append(f"Date:    {sale.created_at:%Y-%m-%d %H:%M}")
    out.append(f"Cashier: {sale.cashier_name}")
    if sale.register_name:
        out.append(f"Register: {sale.register_name}")
    if sale.customer_name:
        out.append(f"Customer: {sale.customer_name}")
    out.append(rule)

    for item in sale.items:
        out += _wrap(item.product_name, width)
        out.append(_row(f"  {item.qty} x {usd(item.unit_price)}", usd(item.qty * item.unit_price), width))
        if item.discount:
            out.append(_row("  Discount", usd(-item.discount), width))
        if item.note:
            out.append(f"  * {item.note}"[:width])
        if item.refunded_qty:
            out.append(_row(f"  Refunded {item.refunded_qty}", usd(-item.refunded_amount), width))
    out.append(rule)

    out.append(_row("Subtotal", usd(sale.subtotal), width))
    if sale.discount_total:
        out.append(_row("Discount", usd(-sale.discount_total), width))
    if sale.tax_total:
        out.append(_row("VAT", usd(sale.tax_total), width))
    out.append(_row("TOTAL", usd(sale.total), width))
    out.append(_row("TOTAL (KHR)", khr(usd_cents_to_khr(sale.total, sale.exchange_rate)), width))
    out.append(rule)

    for p in sale.payments:
        name = f"{METHOD_NAMES.get(p.method, p.method)} {p.currency}"
        out.append(_row(name, usd(p.amount) if p.currency == "USD" else khr(p.amount), width))
        if p.reference:
            out.append(f"  Ref: {p.reference}"[:width])
    if sale.change_due:
        out.append(_row("Change", usd(sale.change_due), width))
        out.append(_row("Change (KHR)", khr(usd_cents_to_khr(sale.change_due, sale.exchange_rate)), width))
    if sale.refunded_total:
        out.append(_row("REFUNDED", usd(-sale.refunded_total), width))
    out.append(rule)

    out.append(f"Rate: 1 USD = {sale.exchange_rate:,} KHR".center(width).rstrip())
    out += [line.center(width).rstrip() for line in _wrap(store.get("receipt_footer", ""), width)]
    return "\n".join(out) + "\n"
