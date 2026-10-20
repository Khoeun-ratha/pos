import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pos_mobile/models.dart';
import 'package:pos_mobile/screens/pos_screen.dart';
import 'package:pos_mobile/state/cart.dart';
import 'package:pos_mobile/state/catalog.dart';
import 'package:pos_mobile/state/held.dart';
import 'package:pos_mobile/state/sales.dart';
import 'package:pos_mobile/state/scan.dart';
import 'package:pos_mobile/state/session.dart';
import 'package:shared_preferences/shared_preferences.dart';

const coke = Product(id: 1, name: 'Coca-Cola 330ml', barcode: '8850999320014', sku: 'DRI-001', price: 75, stockQty: 48);
const biscuits = Product(id: 2, name: 'Imported Biscuits', barcode: '0012345678905', price: 150, stockQty: 10);
const catalog = Catalog(categories: [Category(id: 1, name: 'Drinks')], products: [coke, biscuits]);

const _physical = {
  '0': PhysicalKeyboardKey.digit0, '1': PhysicalKeyboardKey.digit1, '2': PhysicalKeyboardKey.digit2,
  '3': PhysicalKeyboardKey.digit3, '4': PhysicalKeyboardKey.digit4, '5': PhysicalKeyboardKey.digit5,
  '6': PhysicalKeyboardKey.digit6, '7': PhysicalKeyboardKey.digit7, '8': PhysicalKeyboardKey.digit8,
  '9': PhysicalKeyboardKey.digit9,
};
const _logical = {
  '0': LogicalKeyboardKey.digit0, '1': LogicalKeyboardKey.digit1, '2': LogicalKeyboardKey.digit2,
  '3': LogicalKeyboardKey.digit3, '4': LogicalKeyboardKey.digit4, '5': LogicalKeyboardKey.digit5,
  '6': LogicalKeyboardKey.digit6, '7': LogicalKeyboardKey.digit7, '8': LogicalKeyboardKey.digit8,
  '9': LogicalKeyboardKey.digit9,
};

/// A USB scanner: every digit then Enter, all at once. With [khmer] the keyboard layout is Khmer, so the keys
/// arrive as Khmer digits while the physical keys are the barcode's.
Future<void> scanKeys(WidgetTester tester, String code, {bool khmer = false}) async {
  for (final d in code.split('')) {
    final character = khmer ? '០១២៣៤៥៦៧៨៩'[int.parse(d)] : d;
    await simulateKeyDownEvent(_logical[d]!, physicalKey: _physical[d], character: character);
    await simulateKeyUpEvent(_logical[d]!, physicalKey: _physical[d]);
  }
  await simulateKeyDownEvent(LogicalKeyboardKey.enter);
  await simulateKeyUpEvent(LogicalKeyboardKey.enter);
  await tester.pumpAndSettle();
}

class _Catalog extends CatalogNotifier {
  _Catalog(this.offline);
  final bool offline;

  @override
  Future<Catalog> build() async => offline ? Catalog(categories: catalog.categories, products: catalog.products, fromCache: true) : catalog;
}

/// [offline]: the server cannot be reached, so codes are looked up on the phone only.
Future<ProviderContainer> pumpPos(WidgetTester tester, {bool offline = false}) async {
  tester.view.physicalSize = const Size(1280, 800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({
    'server_url': 'http://localhost:8000',
    'token': 'test',
    'user': jsonEncode(const User(id: 3, username: 'cashier', fullName: 'Cashier 1', role: 'cashier').toJson()),
    'settings': jsonEncode(const StoreSettings(storeName: 'Shop', exchangeRate: 4100).toJson()),
    'scan_sound': false,
  });
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(
    ProviderScope(
      retry: (_, _) => null,
      overrides: [
        prefsProvider.overrideWithValue(prefs),
        catalogProvider.overrideWith(() => _Catalog(offline)),
        currentShiftProvider.overrideWith((ref) async => null),
        heldOrdersProvider.overrideWith((ref) async => const []),
      ],
      child: MaterialApp(home: Scaffold(body: PosScreen(onOpenShift: () {}))),
    ),
  );
  await tester.pumpAndSettle();
  return ProviderScope.containerOf(tester.element(find.byType(PosScreen)));
}

int qtyOf(ProviderContainer c, Product p) => c.read(cartProvider).lines.where((l) => l.product.id == p.id).fold(0, (n, l) => n + l.qty);

void main() {
  test('codes: UPC-A / EAN-13, Khmer digits, SKU in any case', () {
    expect(catalog.byCode('8850999320014'), coke);
    expect(catalog.byCode('៨៨៥០៩៩៩៣២០០១៤'), coke);
    expect(catalog.byCode('dri-001'), coke);
    expect(catalog.byCode('012345678905'), biscuits); // UPC-A read of the EAN-13 0012345678905
    expect(catalog.byCode('999'), isNull);
  });

  test('"3*" quantity in front of a code or name', () {
    expect(splitQty('3*8850999320014'), (3, '8850999320014'));
    expect(splitQty('2 x coke'), (2, 'coke'));
    expect(splitQty('coke'), (1, 'coke'));
    expect(isPendingQty('3*'), isTrue);
    expect(isPendingQty('3*coke'), isFalse);
  });

  testWidgets('a USB scanner adds the item wherever the focus is, also with the Khmer keyboard', (tester) async {
    final c = await pumpPos(tester);
    await scanKeys(tester, '8850999320014');
    expect(qtyOf(c, coke), 1);
    await scanKeys(tester, '8850999320014', khmer: true);
    expect(qtyOf(c, coke), 2);
    await scanKeys(tester, '012345678905');
    expect(qtyOf(c, biscuits), 1);
  });

  testWidgets('"3*" typed, then a scan into the search box adds 3', (tester) async {
    final c = await pumpPos(tester);
    final search = find.byType(TextField).first;
    await tester.enterText(search, '3*');
    await tester.pump();
    expect(find.text('Next scan or tap adds 3'), findsOneWidget);
    await tester.enterText(search, '3*8850999320014');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(qtyOf(c, coke), 3);
    expect(tester.widget<TextField>(search).controller!.text, isEmpty);
  });

  testWidgets('an unknown barcode tells a cashier to ask a manager', (tester) async {
    final c = await pumpPos(tester, offline: true);
    final search = find.byType(TextField).first;
    await tester.enterText(search, '1234567890999');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(find.textContaining('Ask a manager to add it'), findsOneWidget);
    expect(c.read(cartProvider).isEmpty, isTrue);
  });

  testWidgets('tap the quantity to type it', (tester) async {
    final c = await pumpPos(tester);
    await scanKeys(tester, '8850999320014');
    await tester.tap(find.byTooltip('Type the quantity'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, '24');
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(qtyOf(c, coke), 24);
  });
}
