# POS System — Vue web + Python service + Flutter mobile + MySQL

A complete Point of Sale system for a retail shop / mini-mart in Cambodia (USD + KHR).

## How to run

**Easiest:** double-click `start_all.bat` in this folder. It starts the service, then the web app,
and opens http://localhost:8080 (login `admin` / `admin123`).

**Or type the commands** — open one PowerShell window per part. Start the **server first**.
Stop any of them with **Ctrl+C**.

### Server (Python FastAPI) — http://localhost:8000 (API docs: /docs)

First time only:

```powershell
cd D:\owner\POS\server
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # then put your MySQL login in .env
```

Run:

```powershell
cd D:\owner\POS\server
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

While coding (reloads on save): add `--reload` to the end of that command.

### Web (Vue) — http://localhost:8080

First time only:

```powershell
cd D:\owner\POS\web
npm install
```

Run:

```powershell
cd D:\owner\POS\web
npm run build
npm run preview
```

While coding (reloads on save): `npm run dev` (same address).

### Mobile (Flutter) — phone or emulator

First time only:

```powershell
cd D:\owner\POS\mobile
flutter pub get
```

Run (connect a phone with USB debugging, or start an emulator first):

```powershell
cd D:\owner\POS\mobile
flutter devices                 # check the phone / emulator is listed
flutter run                     # or: flutter run -d <device id>
```

Server address on the login screen: Android emulator `http://10.0.2.2:8000`; a real phone
`http://<this PC's IP>:8000` (same Wi-Fi). Release build: `flutter build apk --release`.

| Start script (double-click) | What it does |
|---|---|
| `start_all.bat` | service + web app |
| `start_server.bat` | service only |
| `start_web.bat` | web app only |
| `start_mobile.bat` | Flutter app on a phone / emulator |
| `server\migrate.bat` | create / update the `pos_db` tables in MySQL |

```
   web/ (Vue 3)              mobile/ (Flutter)
   browser at :8080          Android / iOS app
          \                       /
           \   REST API (JSON)   /
            v                   v
        server/ (Python FastAPI) :8000
                    |
            MySQL 8  (database pos_db)  <-- open it in Navicat
```

All three parts calculate prices the same way (`server/app/pricing.py`, `web/src/lib/pricing.ts`,
`mobile/lib/core/pricing.dart`). Money is always stored as whole cents / riel.

## Features

- Login with password or quick PIN; roles **admin / manager / cashier**. The admin chooses what managers and
  cashiers may do (**Users & roles → Roles & permissions**): dashboard / reports, see every cashier's sales,
  approve discounts / voids / refunds, products, inventory, suppliers. The service enforces it; the admin always has
  everything. The defaults are the old fixed roles (manager: all of it, cashier: none of it)
- Menu with sub-menus: **Products** (Product list, Barcode & QR labels), **Inventory** (Stock levels, Low stock,
  Stock movements, Stock transfers, Branches & warehouses), **Users & roles** (Users, Roles & permissions).
  Each person only sees what they may use
- Sell screen: product cards, category pills, search, USB barcode scanner (web) / camera scanner (mobile)
- Barcode scanning like a supermarket till, the same on the web app and the mobile app:
  - USB / Bluetooth scanner works wherever the cursor is (even with the Khmer keyboard on) and never presses the
    button that has the focus; scanning while the last receipt is showing starts the next sale
  - camera scanning (web on tablets / phones, and the mobile app): the camera stays open and adds every item as it
    is scanned, shows the item and how many are in the cart, until you tap Done. An item held under the camera is
    added once; scan a second one after taking the first away. The web camera needs https or localhost (browser rule)
  - beep / vibration when the item is added, low buzz when the code is unknown; the speaker button turns sound off;
    the added line flashes in the cart
  - type `3*` then scan (or tap a product) to add 3; tap the quantity in the cart to type it (e.g. 24 for a box)
  - UPC-A (12 digits) and EAN-13 (13 digits, leading 0) of the same product both match; SKUs match too
  - unknown barcode: a manager can create the product right away (the barcode is filled in)
  - keys: `F2` search, `F4` hold, `F12` pay, `Esc` clear search (mobile app too, with a keyboard)
- Hold / resume orders on every till, web and phones alike (held orders are kept on the service). A held order can
  be **sent to another cashier's till** (it shows there as "for you"), or passed on later with the send button
- Barcode / QR labels (web, **Products → Barcode & QR labels**): tick or scan products and print; also the barcode
  button on a product, or **Print labels** for every product listed. Barcode or QR code, with name, price (USD and riel) and shop name; label printer 50 × 30 / 40 × 30 mm,
  58 mm receipt roll (one label per page), or **A4 paper in rows × columns** you choose (2 × 5 up to 6 × 20, with a
  page preview, cut lines, and "skip places already used" for part-used sticker sheets). A product without a barcode gets a new in-store EAN-13
  (starting with 200, numbers kept for shops) with one click, also in the product form
- Discounts per item and per order (cashiers need a **manager PIN**), VAT inclusive or exclusive
- Payments: cash **USD and KHR** (change shown in both), card, KHQR, split payments
- 80mm receipts: print, copy, reprint; optional automatic printing after each sale
- Void items with manager PIN
- Refunds (full or partial) with manager approval; stock goes back automatically
- Shifts: opening cash, cash in/out, close with counted USD + riel, over/short report (printable)
  - **Hand over to next cashier** without emptying the drawer: count together, the next cashier types their own PIN;
    the first shift closes with that count (over / short is theirs) and the next one opens with exactly that cash
  - a manager can count and close a shift its cashier left open; cashiers see their own past shifts and reprint them
- Inventory (web, **Inventory** menu): stock value at cost and selling price, low / out of stock, scan a barcode to
  receive that product; receive stock with cost price and supplier (product cost becomes the average), write off
  damaged / expired / lost stock, stock counts, movement history, low-stock alerts, CSV import / export
- Suppliers: list, and every delivery received from each one
- **Branches & warehouses** (web, Inventory menu): each keeps its own stock; pick the place at the top of Stock levels
  to receive deliveries, write off or count there. The tills sell from the main shop (the store itself)
- **Stock transfers** between the main shop and branches / warehouses: search or scan the products, **send** (the
  stock leaves at once and is "on the road"), then **receive** at the other end, or cancel to put it back. Never
  more than the source has; numbered TRyyyymmdd-0001; printable delivery note; in the stock history of both places.
  Stock value in Reports counts every place and the goods on the road
- Customers with loyalty points and purchase history
- Reports: net sales, profit, daily chart, top products, categories, payment methods, cashiers,
  stock received, stock losses, stock value; **Export Excel** (summary, days, products, every receipt, losses)
- Admin: store settings and shop logo (printed on receipts), users, activity log (who did what and when)
- Web app in **English or Khmer** (EN / ខ្មែរ switch at the top; translations in `web/src/lib/km.ts`)
- Mobile works offline: sales are saved on the phone and synced later (no duplicates)

## How an order works

1. **Open a shift** (count the cash in the drawer). The till takes no payment without one.
2. **Ring up**: tap or scan products. Adding is free; lowering a quantity, removing an item or clearing the
   order is a *void*: a cashier needs a manager PIN once per order, and every void is in the activity log.
3. **Hold** (optional): the order is parked on the service with a name ("Lady in red"). It survives a page
   refresh, shows on every till, and disappears from the list as soon as one till resumes it.
   Throwing a held order away is a void. Closing a shift warns about held orders still waiting.
   **Send to** another cashier: the order shows first on their till, marked "for you" (any till can still finish it).
4. **Pay**: the till first re-checks prices with the service, so the customer pays exactly what is recorded.
   Cash USD / riel (change in both), card or KHQR (optional approval code / transaction ID), or split.
   Retrying after a network error never records the sale twice (each order has one id).
5. **Sale saved**: receipt number, stock goes down, loyalty points added, cash counted in the shift.
   A receipt printed later says **REPRINT / COPY** and is logged.
6. **Refund** (manager PIN): stock goes back, points are taken back, money returns the way it was paid
   (only the cash part leaves the drawer, and that needs an open shift).
7. **Close the shift**: count USD and riel; the report shows expected cash and over / short.
   **Cashier change** instead: *Hand over to next cashier*, count together, the next cashier types their PIN and
   carries on with the same drawer. A shift someone forgot is closed by a manager from the Shift page.

**Phone offline:** the sale is kept on the phone and sent later. The service then keeps the phone's prices and
exchange rate, puts it in the shift that was open at that time, and never refuses it (the customer already paid);
any price difference is written to the activity log.

## 1. Database (MySQL) and Navicat

1. Make sure MySQL 8 is running (Windows service `MySQL80`).
2. Open `server\.env` (created from `.env.example`) and fill in your MySQL login:
   ```
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your-password
   DB_NAME=pos_db
   ```
3. Create the database and tables, either way:
   - **`server\migrate.bat`**: creates `pos_db` and all tables (migrations in `server/migrations`), or
   - **in Navicat**: right-click the MySQL connection → *Execute SQL File* → `server\database\pos_db.sql`.

   The service also runs the migrations by itself on every start, so this step is optional.
   On its first start with empty tables it adds the demo data (`POS_SEED=true`).
4. In **Navicat**: *Connection → MySQL*, host `localhost`, port `3306`, your user/password →
   open `pos_db`. Main tables: `products`, `categories`, `sales`, `sale_items`, `payments`, `refunds`,
   `shifts`, `customers`, `stock_movements`, `users`, `settings`, `audit_logs`.
   Money columns are integers: `price = 75` means **$0.75**; riel columns are whole riel.

To start again with fresh demo data: in Navicat drop the database `pos_db`, then restart the service.
To start with an empty shop, set `POS_SEED=false` in `.env` before the first start.
Demo products get drawn pictures (`server/app/demo_images.py`, saved in `server\uploads\products`).
To add them to demo products that have no photo: `cd server` then `.venv\Scripts\python -m app.demo_images`.

## 2. Start everything

Double-click **`start_all.bat`** (or in PowerShell: `.\start_all.bat`). It opens two windows:

| Window | What | Address |
|---|---|---|
| POS Service | Python FastAPI | http://localhost:8000 (API docs: /docs) |
| POS Web | Vue web app | **http://localhost:8080** |

Or start them one by one: `.\start_server.bat`, then `.\start_web.bat`.

Other PCs, tablets and phones on the shop Wi-Fi can open `http://<this PC's IP>:8080`.
Allow ports 8000 and 8080 in Windows Firewall once (Administrator PowerShell):

```powershell
netsh advfirewall firewall add rule name="POS" dir=in action=allow protocol=TCP localport=8000,8080
```

### Demo logins

| User     | Password     | PIN  | Can do |
|----------|--------------|------|--------|
| admin    | admin123     | 1111 | everything, settings, users, activity log |
| manager  | manager123   | 2222 | products, stock, reports, approvals |
| cashier  | cashier123   | 3333 | sell, shifts, own sales |
| cashier2 | cashier123   | 4444 | same as cashier |

**Change these passwords before real use** (Users page).

## 3. Mobile app (Flutter)

```powershell
cd mobile
flutter run
```

Server address on the login screen: Android emulator `http://10.0.2.2:8000`; a real phone `http://<PC IP>:8000`.
Release build: `flutter build apk --release` (iOS needs a Mac).

## Development

| Part | Folder | Run while coding | Tests |
|---|---|---|---|
| Service | `server/` | `.venv\Scripts\python -m uvicorn app.main:app --reload` | `.venv\Scripts\python -m pytest` |
| Web | `web/` | `npm run dev` (http://localhost:8080, reloads on save) | `npm run build` (type check) and `npm run e2e` (real browser: sell, pay, refund, every page, barcode scanning incl. camera) |
| Mobile | `mobile/` | `flutter run` | `flutter test` |

```
server/  app/main.py, config.py (reads .env), models.py, pricing.py, receipt.py, seed.py, routers/
web/     src/views (Sell, Sales, Shift, Reports, Products, Customers, Settings, Users, Activity),
         src/components/sell (cart, payment, receipt), src/stores (Pinia), src/api, src/lib
mobile/  lib/screens, lib/state (Riverpod), lib/api, lib/core
```

Changing a table: edit `server/app/models.py`, then

```powershell
cd server
.venv\Scripts\alembic revision --autogenerate -m "what changed"   # writes a new file in migrations/versions
.venv\Scripts\alembic upgrade head                                  # applies it to pos_db
```

`tests/test_migrations.py` fails if a model changes without a migration.

Service settings (`server/.env`): `DB_*` (MySQL), `POS_SEED`, `POS_JWT_SECRET` (random if empty),
`POS_DATABASE_URL` (overrides `DB_*`, e.g. `sqlite:///./pos.db` to run without MySQL).
