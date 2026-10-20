"""Cart math. Pure functions, integer money only (USD cents / KHR riel).

Percent discounts and tax rates are in basis points: 1000 = 10.00%.
"""

from dataclasses import dataclass

PERCENT = "percent"
AMOUNT = "amount"


def div_round(numerator: int, denominator: int) -> int:
    """Integer division rounding half up (inputs are non-negative)."""
    return (2 * numerator + denominator) // (2 * denominator)


def discount_of(base: int, kind: str | None, value: int) -> int:
    if not kind or value <= 0 or base <= 0:
        return 0
    if kind == PERCENT:
        return min(base, div_round(base * min(value, 10000), 10000))
    if kind == AMOUNT:
        return min(base, value)
    raise ValueError(f"Unknown discount type: {kind}")


@dataclass
class LineInput:
    unit_price: int
    qty: int
    discount_type: str | None = None
    discount_value: int = 0


@dataclass
class LineResult:
    gross: int
    discount: int  # own discount + share of the order discount
    tax: int
    total: int


@dataclass
class CartTotals:
    subtotal: int
    discount_total: int
    tax_total: int
    total: int
    lines: list[LineResult]


def share_of(done_before: int, part: int, portion: int, whole: int) -> int:
    """`portion`'s share of `part`, when `done_before` of `whole` was already taken. Taking the shares
    one after another adds up to exactly `portion` (e.g. the cash part of several partial refunds)."""
    if whole <= 0:
        return 0
    return div_round((done_before + part) * portion, whole) - div_round(done_before * portion, whole)


def allocate(amount: int, weights: list[int]) -> list[int]:
    """Split `amount` across weights proportionally; parts always sum to `amount`."""
    weight_sum = sum(weights)
    if amount <= 0 or weight_sum <= 0:
        return [0] * len(weights)
    shares = [amount * w // weight_sum for w in weights]
    remainders = sorted(range(len(weights)), key=lambda i: amount * weights[i] % weight_sum, reverse=True)
    for i in remainders[: amount - sum(shares)]:
        shares[i] += 1
    return shares


def calculate(
    lines: list[LineInput],
    order_discount_type: str | None = None,
    order_discount_value: int = 0,
    tax_rate_bp: int = 0,
    tax_inclusive: bool = False,
) -> CartTotals:
    gross = [line.unit_price * line.qty for line in lines]
    line_discounts = [discount_of(g, line.discount_type, line.discount_value) for g, line in zip(gross, lines)]
    nets = [g - d for g, d in zip(gross, line_discounts)]

    order_discount = discount_of(sum(nets), order_discount_type, order_discount_value)
    order_shares = allocate(order_discount, nets)

    results: list[LineResult] = []
    for g, line_disc, net, share in zip(gross, line_discounts, nets, order_shares):
        taxable = net - share
        if tax_inclusive:
            tax = taxable - div_round(taxable * 10000, 10000 + tax_rate_bp)
            total = taxable
        else:
            tax = div_round(taxable * tax_rate_bp, 10000)
            total = taxable + tax
        results.append(LineResult(gross=g, discount=line_disc + share, tax=tax, total=total))

    return CartTotals(
        subtotal=sum(gross),
        discount_total=sum(r.discount for r in results),
        tax_total=sum(r.tax for r in results),
        total=sum(r.total for r in results),
        lines=results,
    )


def khr_to_usd_cents(riel: int, rate: int) -> int:
    return div_round(riel * 100, rate)


def usd_cents_to_khr(cents: int, rate: int, round_to: int = 100) -> int:
    """Convert cents to riel, rounded to the nearest `round_to` riel (smallest note in use)."""
    return div_round(cents * rate, 100 * round_to) * round_to
