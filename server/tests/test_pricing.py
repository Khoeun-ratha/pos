from app.pricing import (
    AMOUNT,
    PERCENT,
    LineInput,
    allocate,
    calculate,
    div_round,
    khr_to_usd_cents,
    usd_cents_to_khr,
)


def test_div_round_half_up():
    assert div_round(5, 2) == 3
    assert div_round(4, 3) == 1
    assert div_round(0, 7) == 0


def test_allocate_sums_exactly():
    shares = allocate(100, [1, 1, 1])
    assert sum(shares) == 100
    assert sorted(shares) == [33, 33, 34]
    assert allocate(0, [5, 5]) == [0, 0]


def test_exclusive_tax():
    totals = calculate([LineInput(75, 2), LineInput(120, 1)], tax_rate_bp=1000)
    assert totals.subtotal == 270
    assert totals.tax_total == 27
    assert totals.total == 297


def test_inclusive_tax_keeps_price():
    totals = calculate([LineInput(110, 1)], tax_rate_bp=1000, tax_inclusive=True)
    assert totals.total == 110
    assert totals.tax_total == 10


def test_line_and_order_discounts():
    lines = [LineInput(1000, 1, PERCENT, 1000), LineInput(500, 2, AMOUNT, 100)]
    totals = calculate(lines, AMOUNT, 200, tax_rate_bp=0)
    # line discounts: 100 + 100; order discount 200 split over nets 900 / 900
    assert totals.discount_total == 400
    assert totals.total == 1600
    assert [line.discount for line in totals.lines] == [200, 200]


def test_discount_never_exceeds_price():
    totals = calculate([LineInput(100, 1, AMOUNT, 999)], PERCENT, 5000)
    assert totals.total == 0
    assert totals.discount_total == 100


def test_currency_conversion():
    assert khr_to_usd_cents(4100, 4100) == 100
    assert usd_cents_to_khr(125, 4100) == 5100  # 5125 riel -> nearest 100
    assert usd_cents_to_khr(0, 4100) == 0
