"""Demo data, created only when the database has no users.

With demo_history=True (the default for a real start) it also creates customers and 30 days of
sales, shifts and refunds so every screen and report has something to show.
"""

import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import store_settings
from .demo_images import add_demo_images
from .models import (
    Category,
    Customer,
    Expense,
    Payment,
    Product,
    Refund,
    RefundItem,
    Register,
    Sale,
    SaleItem,
    Shift,
    StockMovement,
    User,
)
from .pricing import PERCENT, LineInput, calculate, div_round, khr_to_usd_cents, share_of, usd_cents_to_khr
from .security import hash_pin, hash_secret

DEMO_USERS = [
    # username, password, PIN, role, full name
    ("admin", "admin123", "1111", "admin", "Owner"),
    ("manager", "manager123", "2222", "manager", "Store Manager"),
    ("cashier", "cashier123", "3333", "cashier", "Cashier 1"),
    ("cashier2", "cashier123", "4444", "cashier", "Cashier 2"),
]

# name, barcode, price (cents), cost (cents), stock now
DEMO_PRODUCTS = {
    "Drinks": [
        ("Coca-Cola 330ml", "8850999320014", 75, 45, 48),
        ("Angkor Beer 330ml", "8846000101012", 100, 65, 96),
        ("Mineral Water 500ml", "8846000200012", 35, 15, 120),
        ("Iced Coffee", "2000000000015", 150, 60, 0),
        ("Red Bull 250ml", "8850228000016", 90, 60, 36),
        ("Sprite 330ml", "8850999320021", 75, 45, 40),
        ("Cambodia Beer 330ml", "8846000101029", 100, 62, 72),
        ("Green Tea 500ml", "8850999330013", 90, 55, 30),
        ("Fresh Milk 1L", "8850329100018", 210, 160, 14),
        ("Orange Juice 1L", "8850329200015", 250, 180, 9),
    ],
    "Snacks": [
        ("Lay's Classic 50g", "8850718801213", 120, 80, 30),
        ("Oreo 133g", "8850096330014", 150, 100, 24),
        ("Peanuts 100g", "2000000000022", 80, 40, 4),
        ("Pringles Original 107g", "5053990101016", 280, 200, 18),
        ("KitKat 4 Finger", "8850125070011", 90, 60, 40),
        ("Dried Mango 100g", "2000000000046", 200, 120, 12),
        ("Cup Cake Vanilla", "8850125080010", 50, 30, 2),
    ],
    "Groceries": [
        ("Jasmine Rice 5kg", "8850001500017", 650, 520, 15),
        ("Mama Instant Noodles", "8850987101014", 25, 15, 200),
        ("Fish Sauce 700ml", "8850002700011", 180, 120, 18),
        ("Eggs (10 pcs)", "2000000000039", 160, 120, 3),
        ("Cooking Oil 1L", "8850002800018", 290, 230, 20),
        ("Sugar 1kg", "8850002900015", 120, 90, 25),
        ("Kampot Pepper 100g", "2000000000053", 450, 300, 8),
        ("Canned Sardines", "8850003000011", 110, 75, 36),
    ],
    "Personal Care": [
        ("Colgate Toothpaste 150g", "8850006320017", 220, 150, 12),
        ("Sunsilk Shampoo 320ml", "8851932300015", 350, 250, 10),
        ("Lux Soap 85g", "8851932400012", 60, 40, 45),
        ("Toothbrush Soft", "8850006330016", 120, 70, 22),
        ("Tissue Box 150 sheets", "8850006400016", 130, 90, 4),
    ],
    "Household": [
        ("Dish Soap 500ml", "8851932500019", 150, 100, 16),
        ("Laundry Powder 900g", "8851932600016", 380, 290, 11),
        ("Trash Bags (30 pcs)", "2000000000060", 160, 100, 20),
        ("AA Batteries (4 pcs)", "8888021100012", 250, 160, 15),
        ("Mosquito Coil (10 pcs)", "8850011100014", 140, 90, 1),
    ],
}

DEMO_CUSTOMERS = [
    ("Sok Dara", "012345101"),
    ("Chan Sreymom", "012345102"),
    ("Kim Visal", "012345103"),
    ("Heng Sophea", "012345104"),
    ("Lim Rathana", "012345105"),
    ("Touch Bopha", "012345106"),
    ("Mao Pisey", "012345107"),
    ("Chea Vuthy", "012345108"),
    ("Nget Sokha", "012345109"),
    ("Ly Kimheng", "012345110"),
]

HISTORY_DAYS = 30
USD_NOTES = [100, 500, 1000, 2000, 5000, 10000]


def seed(db: Session, demo_history: bool = True, demo_images: bool = True) -> None:
    if db.scalar(select(User.id).limit(1)):
        return

    users = {}
    for username, password, pin, role, full_name in DEMO_USERS:
        users[username] = User(username=username, password_hash=hash_secret(password), pin_hash=hash_pin(pin),
                               role=role, full_name=full_name)
        db.add(users[username])

    # tills: the database update makes Counter 1; the demo has a second counter, one per demo cashier
    registers = list(db.scalars(select(Register).order_by(Register.id))) or [Register(name="Counter 1")]
    if demo_history and len(registers) < 2:
        registers.append(Register(name="Counter 2"))
    db.add_all(registers)

    products: list[Product] = []
    for order, (category_name, items) in enumerate(DEMO_PRODUCTS.items()):
        category = Category(name=category_name, sort_order=order)
        db.add(category)
        db.flush()
        for index, (name, barcode, price, cost, stock) in enumerate(items, start=1):
            product = Product(
                name=name, barcode=barcode, sku=f"{category_name[:3].upper()}-{index:03d}", category_id=category.id,
                price=price, cost=cost, stock_qty=stock, track_stock=name != "Iced Coffee",
            )
            db.add(product)
            products.append(product)
    db.flush()

    if demo_history and demo_images:
        add_demo_images(db, products)  # pictures in server/uploads
    if demo_history:
        _history(db, users, products, registers)
    else:
        for product in products:
            if product.stock_qty:
                db.add(StockMovement(product_id=product.id, change=product.stock_qty, balance=product.stock_qty,
                                     kind="stock_in", note="Demo data"))
    db.commit()


def _history(db: Session, users: dict[str, User], products: list[Product], registers: list[Register]) -> None:
    """30 days of believable trading. Stock ends exactly at the levels listed in DEMO_PRODUCTS."""
    rng = random.Random(2026)
    rate = int(store_settings.DEFAULTS["exchange_rate"])
    tax_bp = int(store_settings.DEFAULTS["tax_rate_bp"])
    today = date.today()
    current = datetime.now().replace(microsecond=0)

    joined = current - timedelta(days=HISTORY_DAYS)  # before their first purchase
    customers = [Customer(name=name, phone=phone, created_at=joined) for name, phone in DEMO_CUSTOMERS]
    db.add_all(customers)
    db.flush()

    # cheap everyday items sell more often
    weights = [max(1, 600 // p.price) for p in products]
    sales: list[Sale] = []
    shifts: list[Shift] = []
    sold = {p.id: 0 for p in products}

    for days_ago in range(HISTORY_DAYS - 1, -1, -1):
        day = today - timedelta(days=days_ago)
        cashier, register = (users["cashier"], registers[0]) if days_ago % 2 == 0 else (users["cashier2"], registers[1])
        opened = datetime.combine(day, time(7, 0))
        if opened > current:
            continue
        shift = Shift(user_id=cashier.id, register_id=register.id, opened_at=opened, opening_cash=2000)
        db.add(shift)
        db.flush()
        shifts.append(shift)

        last_minute = 21 * 60 if days_ago else min(21 * 60, current.hour * 60 + current.minute - 1)
        count = rng.randint(14, 24) if day.weekday() >= 5 else rng.randint(9, 16)
        if days_ago == 0:
            count = count * max(0, last_minute - 7 * 60) // (14 * 60)
        minutes = sorted(rng.randint(7 * 60 + 5, last_minute) for _ in range(count)) if last_minute > 7 * 60 + 5 else []

        for number, minute in enumerate(minutes, start=1):
            created = datetime.combine(day, time(minute // 60, minute % 60, rng.randint(0, 59)))
            picked = {p.id: p for p in rng.choices(products, weights=weights, k=rng.choice([1, 1, 2, 2, 3, 4]))}
            lines = [(p, rng.choice([1, 1, 1, 2, 2, 3])) for p in picked.values()]

            discount = rng.choice([500, 1000]) if rng.random() < 0.08 else 0
            totals = calculate([LineInput(p.price, qty) for p, qty in lines],
                               PERCENT if discount else None, discount, tax_bp, False)
            payments = _payments(rng, totals.total, rate)
            paid = sum(p.amount_usd for p in payments)
            customer = rng.choice(customers) if rng.random() < 0.3 else None
            if customer:
                customer.points += totals.total // 100

            sale = Sale(
                # every sale goes into the drawer of the shift open at that time, as on a real till
                receipt_no=f"{day:%Y%m%d}-{number:04d}", user_id=cashier.id, shift_id=shift.id,
                customer_id=customer.id if customer else None,
                subtotal=totals.subtotal, discount_total=totals.discount_total, tax_total=totals.tax_total,
                total=totals.total, paid_total=paid, change_due=max(0, paid - totals.total),
                exchange_rate=rate, created_at=created, payments=payments,
                items=[
                    SaleItem(product_id=p.id, product_name=p.name, qty=qty, unit_price=p.price, unit_cost=p.cost,
                             discount=line.discount, tax=line.tax, line_total=line.total)
                    for (p, qty), line in zip(lines, totals.lines)
                ],
            )
            db.add(sale)
            sales.append(sale)
            for p, qty in lines:
                sold[p.id] += qty
    db.flush()

    refunds = _refunds(db, rng, sales, users["manager"])
    _stock_history(db, products, sales, refunds, sold, today)
    _close_shifts(db, rng, shifts, sales, refunds, current)
    _expenses(db, rng, users["manager"], today)


def _payments(rng: random.Random, total: int, rate: int) -> list[Payment]:
    roll = rng.random()
    if roll < 0.15:
        return [Payment(method="card", currency="USD", amount=total, amount_usd=total)]
    if roll < 0.35:
        return [Payment(method="khqr", currency="USD", amount=total, amount_usd=total)]
    if roll < 0.55:  # cash in riel, rounded up to the next 5,000 note
        riel = (usd_cents_to_khr(total, rate) + 4999) // 5000 * 5000
        return [Payment(method="cash", currency="KHR", amount=riel, amount_usd=khr_to_usd_cents(riel, rate))]
    amount = next((note for note in USD_NOTES if note >= total), (total + 999) // 1000 * 1000)
    return [Payment(method="cash", currency="USD", amount=amount, amount_usd=amount)]


def _cash_kept(sale: Sale) -> int:
    return min(max(sum(p.amount_usd for p in sale.payments if p.method == "cash") - sale.change_due, 0), sale.total)


def _refunds(db: Session, rng: random.Random, sales: list[Sale], manager: User) -> list[tuple[Refund, Sale, SaleItem]]:
    """A few customers bring something back a little later the same day."""
    done = []
    candidates = [s for s in sales if s.created_at.date() < date.today() and s.shift_id]
    for sale in rng.sample(candidates, k=min(4, len(candidates))):
        item = sale.items[0]
        amount = item.line_total if item.qty == 1 else div_round(item.line_total, item.qty)
        refund = Refund(sale_id=sale.id, user_id=sale.user_id, approved_by_id=manager.id, shift_id=sale.shift_id,
                        amount=amount, cash_amount=share_of(0, amount, _cash_kept(sale), sale.total),
                        reason=rng.choice(["Damaged", "Expired", "Wrong item"]),
                        created_at=sale.created_at + timedelta(minutes=45))
        db.add(refund)
        db.flush()
        db.add(RefundItem(refund_id=refund.id, sale_item_id=item.id, qty=1, amount=amount))
        item.refunded_qty = 1
        item.refunded_amount = amount
        sale.refunded_total = amount
        sale.status = "refunded" if len(sale.items) == 1 and item.qty == 1 else "partially_refunded"
        done.append((refund, sale, item))
    return done


def _stock_history(db, products, sales, refunds, sold, today) -> None:
    """Opening delivery 30 days ago, then every sale and refund, ending at today's demo levels."""
    refunded = {}
    for _, _, item in refunds:
        refunded[item.product_id] = refunded.get(item.product_id, 0) + 1
    balance = {}
    start = datetime.combine(today - timedelta(days=HISTORY_DAYS), time(6, 0))
    for p in products:
        if not p.track_stock:
            continue
        balance[p.id] = p.stock_qty + sold[p.id] - refunded.get(p.id, 0)
        db.add(StockMovement(product_id=p.id, change=balance[p.id], balance=balance[p.id], kind="stock_in",
                             note="Opening delivery (demo)", created_at=start))

    events = [(s.created_at, s.receipt_no, item.product_id, -item.qty, "sale") for s in sales for item in s.items]
    events += [(r.created_at, s.receipt_no, item.product_id, 1, "refund") for r, s, item in refunds]
    for created, receipt, product_id, change, kind in sorted(events, key=lambda e: e[0]):
        if product_id not in balance:
            continue
        balance[product_id] += change
        db.add(StockMovement(product_id=product_id, change=change, balance=balance[product_id], kind=kind,
                             reference=receipt, created_at=created))


def _expenses(db: Session, rng: random.Random, manager: User, today: date) -> None:
    """A month of shop costs: the monthly bills on the 1st, ice and supplies every few days."""
    for days_ago in range(HISTORY_DAYS - 1, -1, -1):
        day = today - timedelta(days=days_ago)
        # the 1st of the month, or the first day shown when the 30 days hold no 1st
        if day.day == 1 or (days_ago == HISTORY_DAYS - 1 and today.day == 31):
            for category, amount, note in (("Rent", 30000, "Shop rent"), ("Salaries", 44000, "2 cashiers"),
                                           ("Electricity", rng.randint(4500, 6000), "EDC bill"), ("Water", 800, None),
                                           ("Internet & phone", 1500, None)):
                db.add(Expense(spent_on=day, category=category, amount=amount, note=note, user_id=manager.id))
        if days_ago % 3 == 0:
            db.add(Expense(spent_on=day, category="Ice & supplies", amount=rng.randint(200, 450), note="Ice", user_id=manager.id))


def _close_shifts(db, rng, shifts, sales, refunds, current) -> None:
    """Every past shift is closed and counted; today's shift stays open for the cashier."""
    for shift in shifts:
        if shift.opened_at.date() == current.date():
            continue
        shift_sales = [s for s in sales if s.shift_id == shift.id]
        cash = sum(p.amount_usd for s in shift_sales for p in s.payments if p.method == "cash")
        cash -= sum(s.change_due for s in shift_sales)
        cash -= sum(r.amount for r, _, _ in refunds if r.shift_id == shift.id)
        shift.expected_cash = shift.opening_cash + cash
        shift.counted_cash = shift.expected_cash + rng.choice([0, 0, 0, 0, -100, 50, -25])
        shift.closed_at = datetime.combine(shift.opened_at.date(), time(21, 30))
