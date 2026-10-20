import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pos_mobile/models.dart';
import 'package:pos_mobile/screens/checkout_screen.dart';
import 'package:pos_mobile/screens/customers_screen.dart';
import 'package:pos_mobile/screens/home_shell.dart';
import 'package:pos_mobile/screens/products_screen.dart';
import 'package:pos_mobile/screens/reports_screen.dart';
import 'package:pos_mobile/state/cart.dart';
import 'package:pos_mobile/state/catalog.dart';
import 'package:pos_mobile/state/sales.dart';
import 'package:pos_mobile/state/session.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Opens every screen at phone, tablet, laptop and desktop sizes with demo data.
/// Any overflow ("RenderFlex overflowed") or layout error fails the test.
const sizes = {'phone': Size(390, 844), 'tablet': Size(820, 1180), 'laptop': Size(1280, 720), 'desktop': Size(1920, 1080)};

const manager = User(id: 2, username: 'manager', fullName: 'Store Manager', role: 'manager');
const settings = StoreSettings(storeName: 'My Mini Mart', taxRateBp: 1000, exchangeRate: 4100);

final categories = [
  for (final (i, n) in ['Drinks', 'Snacks', 'Groceries', 'Personal Care', 'Household'].indexed) Category(id: i + 1, name: n),
];
final products = [
  for (var i = 0; i < 35; i++)
    Product(
      id: i + 1,
      name: '${['Coca-Cola 330ml', 'Laundry Powder 900g', 'Pringles Original 107g', 'Mosquito Coil (10 pcs)', 'Eggs'][i % 5]} #$i',
      barcode: '88500000${i.toString().padLeft(5, '0')}',
      categoryId: i % 5 + 1,
      categoryName: categories[i % 5].name,
      price: 75 + i * 37,
      cost: 50 + i * 20,
      stockQty: i * 3 % 40,
      imageUrl: i % 4 == 0 ? '/uploads/products/$i-test.webp' : null, // fails to load in tests: shows the icon
    ),
];

class _Catalog extends CatalogNotifier {
  @override
  Future<Catalog> build() async => Catalog(categories: categories, products: products);
}

class _Cart extends CartNotifier {
  @override
  Cart build() => Cart(lines: [for (final p in products.take(6)) CartLine(product: p, qty: 2)]);
}

final shift = ShiftReport(
  id: 1,
  cashierName: 'Cashier 1',
  openedAt: DateTime(2026, 10, 15, 7),
  isOpen: true,
  salesCount: 14,
  openingCash: 2000,
  cashSales: 15230,
  cardSales: 4410,
  khqrSales: 6120,
  cashIn: 1000,
  cashOut: 250,
  cashRefunds: 110,
  expectedCash: 17870,
);

final report = ReportSummary(
  salesCount: 422,
  grossSales: 174090,
  refunds: 350,
  netSales: 173740,
  tax: 15800,
  discounts: 2210,
  profit: 54279,
  averageSale: 412,
  byPayment: const [NameAmount('Cash', 0, 300, 120000), NameAmount('KHQR', 0, 80, 35000), NameAmount('Card', 0, 42, 19000)],
  byCategory: [for (final c in categories) NameAmount(c.name, 120, 0, 30000)],
  topProducts: [for (final p in products.take(10)) NameAmount(p.name, 40, 0, 9000)],
  byDay: [for (var d = 0; d < 30; d++) (day: DateTime(2026, 9, 16 + d), amount: 4000 + d * 97 % 3000)],
);

final saleSummaries = [
  for (var i = 1; i <= 25; i++)
    SaleSummary(
      id: i,
      receiptNo: '20261015-${i.toString().padLeft(4, '0')}',
      cashierName: 'Cashier 1',
      customerName: i % 3 == 0 ? 'Chan Sreymom' : null,
      total: 300 + i * 41,
      refundedTotal: i == 4 ? 100 : 0,
      status: i == 4 ? 'partially_refunded' : 'completed',
      createdAt: DateTime(2026, 10, 15, 8, i),
    ),
];

final sale = Sale(
  id: 1,
  receiptNo: '20261015-0001',
  cashierName: 'Cashier 1',
  customerName: 'Sok Dara',
  subtotal: 1500,
  discountTotal: 150,
  taxTotal: 135,
  total: 1485,
  paidTotal: 2000,
  changeDue: 515,
  changeDueKhr: 21100,
  refundedTotal: 0,
  status: 'completed',
  createdAt: DateTime(2026, 10, 15, 9, 30),
  items: [
    for (final p in products.take(4))
      SaleItem(id: p.id, productName: p.name, qty: 2, unitPrice: p.price, discount: 0, lineTotal: p.price * 2, refundedQty: 0),
  ],
  payments: const [Payment(method: 'cash', currency: 'USD', amount: 2000, amountUsd: 2000)],
);

Future<void> pumpScreen(WidgetTester tester, Size size, Widget home) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  SharedPreferences.setMockInitialValues({
    'server_url': 'http://localhost:8000',
    'token': 'test',
    'user': jsonEncode(manager.toJson()),
    'settings': jsonEncode(settings.toJson()),
  });
  final prefs = await SharedPreferences.getInstance();

  await tester.pumpWidget(
    ProviderScope(
      retry: (_, _) => null,
      overrides: [
        prefsProvider.overrideWithValue(prefs),
        catalogProvider.overrideWith(_Catalog.new),
        cartProvider.overrideWith(_Cart.new),
        currentShiftProvider.overrideWith((ref) async => shift),
        reportProvider.overrideWith((ref, days) async => report),
        lowStockProvider.overrideWith((ref) async => products.where((p) => p.isLowStock).toList()),
        salesOfDayProvider.overrideWith((ref, day) async => saleSummaries),
        saleProvider.overrideWith((ref, id) async => sale),
        allProductsProvider.overrideWith((ref) async => products),
        customerSearchProvider.overrideWith(
          (ref, q) async => [for (var i = 0; i < 10; i++) Customer(id: i, name: 'Customer $i', phone: '01234510$i', points: i * 7)],
        ),
      ],
      child: MaterialApp(home: home),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  const sections = ['POS', 'Sales', 'Shift', 'Reports', 'Products', 'Customers', 'Store settings', 'Sync & account'];

  for (final MapEntry(key: name, value: size) in sizes.entries) {
    testWidgets('every menu section fits on $name', (tester) async {
      await pumpScreen(tester, size, const HomeShell());
      final wide = size.width >= 800;

      for (final section in sections) {
        if (!wide) {
          await tester.tap(find.byTooltip('Open navigation menu'));
          await tester.pumpAndSettle();
        }
        await tester.tap(find.widgetWithText(ListTile, section).first);
        await tester.pumpAndSettle();
        expect(find.widgetWithText(AppBar, section), findsOneWidget, reason: '$section on $name');
      }

      // sales: wide screens show the details beside the list
      if (!wide) {
        await tester.tap(find.byTooltip('Open navigation menu'));
        await tester.pumpAndSettle();
      }
      await tester.tap(find.widgetWithText(ListTile, 'Sales').first);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('20261015-0001').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('20261015-0001').first);
      await tester.pumpAndSettle();
      expect(find.text('Refund'), findsOneWidget);
    });

    testWidgets('payment screen fits on $name and completes with Exact', (tester) async {
      await pumpScreen(tester, size, const CheckoutScreen());
      expect(find.textContaining('Add the customer'), findsOneWidget);

      await tester.ensureVisible(find.textContaining(RegExp(r'^Exact ')));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining(RegExp(r'^Exact ')));
      await tester.pumpAndSettle();
      expect(find.text('Change to give'), findsOneWidget);
      final complete = tester.widget<ButtonStyleButton>(
        find.ancestor(of: find.text('Complete sale'), matching: find.bySubtype<ButtonStyleButton>()),
      );
      expect(complete.onPressed, isNotNull);
    });
  }
}
