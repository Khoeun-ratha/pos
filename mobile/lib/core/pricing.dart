import 'money.dart';

/// Mirror of server/app/pricing.py so the cart shows the same totals offline.
/// Percent discounts and tax rates are basis points: 1000 = 10%.
enum DiscountType { percent, amount }

int discountOf(int base, DiscountType? type, int value) {
  if (type == null || value <= 0 || base <= 0) return 0;
  return switch (type) {
    DiscountType.percent => divRound(base * (value > 10000 ? 10000 : value), 10000).clamp(0, base),
    DiscountType.amount => value.clamp(0, base),
  };
}

List<int> allocate(int amount, List<int> weights) {
  final sum = weights.fold(0, (a, b) => a + b);
  if (amount <= 0 || sum <= 0) return List.filled(weights.length, 0);
  final shares = [for (final w in weights) amount * w ~/ sum];
  final order = List.generate(weights.length, (i) => i)..sort((a, b) => (amount * weights[b] % sum).compareTo(amount * weights[a] % sum));
  var left = amount - shares.fold(0, (a, b) => a + b);
  for (final i in order) {
    if (left == 0) break;
    shares[i]++;
    left--;
  }
  return shares;
}

class LineInput {
  const LineInput(this.unitPrice, this.qty, [this.discountType, this.discountValue = 0]);
  final int unitPrice;
  final int qty;
  final DiscountType? discountType;
  final int discountValue;
}

class LineResult {
  const LineResult({required this.gross, required this.discount, required this.tax, required this.total});
  final int gross, discount, tax, total;
}

class CartTotals {
  const CartTotals({required this.subtotal, required this.discountTotal, required this.taxTotal, required this.total, required this.lines});
  final int subtotal, discountTotal, taxTotal, total;
  final List<LineResult> lines;

  static const empty = CartTotals(subtotal: 0, discountTotal: 0, taxTotal: 0, total: 0, lines: []);
}

CartTotals calculate(
  List<LineInput> lines, {
  DiscountType? orderDiscountType,
  int orderDiscountValue = 0,
  int taxRateBp = 0,
  bool taxInclusive = false,
}) {
  final gross = [for (final l in lines) l.unitPrice * l.qty];
  final lineDiscounts = [for (var i = 0; i < lines.length; i++) discountOf(gross[i], lines[i].discountType, lines[i].discountValue)];
  final nets = [for (var i = 0; i < lines.length; i++) gross[i] - lineDiscounts[i]];
  final orderDiscount = discountOf(nets.fold(0, (a, b) => a + b), orderDiscountType, orderDiscountValue);
  final shares = allocate(orderDiscount, nets);

  final results = <LineResult>[];
  for (var i = 0; i < lines.length; i++) {
    final taxable = nets[i] - shares[i];
    final int tax, total;
    if (taxInclusive) {
      tax = taxable - divRound(taxable * 10000, 10000 + taxRateBp);
      total = taxable;
    } else {
      tax = divRound(taxable * taxRateBp, 10000);
      total = taxable + tax;
    }
    results.add(LineResult(gross: gross[i], discount: lineDiscounts[i] + shares[i], tax: tax, total: total));
  }

  int sum(int Function(LineResult) f) => results.fold(0, (a, r) => a + f(r));
  return CartTotals(
    subtotal: gross.fold(0, (a, b) => a + b),
    discountTotal: sum((r) => r.discount),
    taxTotal: sum((r) => r.tax),
    total: sum((r) => r.total),
    lines: results,
  );
}
