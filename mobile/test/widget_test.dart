import 'package:flutter_test/flutter_test.dart';
import 'package:pos_mobile/core/money.dart';
import 'package:pos_mobile/core/pricing.dart';

/// Same cases as server/tests/test_pricing.py: both sides must agree on every cent.
void main() {
  test('rounds half up', () {
    expect(divRound(5, 2), 3);
    expect(divRound(4, 3), 1);
  });

  test('allocation always sums to the amount', () {
    final shares = allocate(100, [1, 1, 1]);
    expect(shares.reduce((a, b) => a + b), 100);
    expect([...shares]..sort(), [33, 33, 34]);
  });

  test('exclusive tax', () {
    final t = calculate([const LineInput(75, 2), const LineInput(120, 1)], taxRateBp: 1000);
    expect([t.subtotal, t.taxTotal, t.total], [270, 27, 297]);
  });

  test('inclusive tax keeps the price', () {
    final t = calculate([const LineInput(110, 1)], taxRateBp: 1000, taxInclusive: true);
    expect([t.total, t.taxTotal], [110, 10]);
  });

  test('line and order discounts', () {
    final t = calculate(
      [const LineInput(1000, 1, DiscountType.percent, 1000), const LineInput(500, 2, DiscountType.amount, 100)],
      orderDiscountType: DiscountType.amount,
      orderDiscountValue: 200,
    );
    expect(t.discountTotal, 400);
    expect(t.total, 1600);
    expect(t.lines.map((l) => l.discount), [200, 200]);
  });

  test('discount never exceeds the price', () {
    final t = calculate(
      [const LineInput(100, 1, DiscountType.amount, 999)],
      orderDiscountType: DiscountType.percent,
      orderDiscountValue: 5000,
    );
    expect([t.total, t.discountTotal], [0, 100]);
  });

  test('currency conversion', () {
    expect(khrToUsdCents(4100, 4100), 100);
    expect(usdCentsToKhr(125, 4100), 5100);
    expect(parseDollars('12.5'), 1250);
    expect(parseDollars('abc'), isNull);
  });
}
