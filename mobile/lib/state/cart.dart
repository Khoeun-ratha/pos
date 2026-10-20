import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/pricing.dart';
import '../models.dart';
import 'session.dart';

/// The product the last tap or scan added, and a number that changes on every add, so the cart can show it.
class LastAddedNotifier extends Notifier<(int productId, int seq)?> {
  int _seq = 0;

  @override
  (int, int)? build() => null;

  void mark(int productId) => state = (productId, ++_seq);
}

final lastAddedProvider = NotifierProvider<LastAddedNotifier, (int, int)?>(LastAddedNotifier.new);

class CartLine {
  const CartLine({required this.product, this.qty = 1, this.discountType, this.discountValue = 0});

  final Product product;
  final int qty;
  final DiscountType? discountType;
  final int discountValue;

  bool get hasDiscount => discountType != null && discountValue > 0;

  CartLine copyWith({int? qty, DiscountType? discountType, int? discountValue, bool clearDiscount = false}) => CartLine(
    product: product,
    qty: qty ?? this.qty,
    discountType: clearDiscount ? null : discountType ?? this.discountType,
    discountValue: clearDiscount ? 0 : discountValue ?? this.discountValue,
  );
}

class Cart {
  const Cart({this.lines = const [], this.discountType, this.discountValue = 0, this.customer, this.managerPin});

  final List<CartLine> lines;
  final DiscountType? discountType;
  final int discountValue;
  final Customer? customer;

  /// PIN of the manager who approved a cashier's discount; sent with the sale.
  final String? managerPin;

  bool get isEmpty => lines.isEmpty;
  int get itemCount => lines.fold(0, (sum, l) => sum + l.qty);
  bool get hasOrderDiscount => discountType != null && discountValue > 0;
  bool get hasAnyDiscount => hasOrderDiscount || lines.any((l) => l.hasDiscount);
}

class CartNotifier extends Notifier<Cart> {
  @override
  Cart build() => const Cart();

  Cart _with({
    List<CartLine>? lines,
    DiscountType? discountType,
    int? discountValue,
    bool clearDiscount = false,
    Customer? customer,
    bool clearCustomer = false,
    String? managerPin,
    bool clearManagerPin = false,
  }) => Cart(
    lines: lines ?? state.lines,
    discountType: clearDiscount ? null : discountType ?? state.discountType,
    discountValue: clearDiscount ? 0 : discountValue ?? state.discountValue,
    customer: clearCustomer ? null : customer ?? state.customer,
    managerPin: clearManagerPin ? null : managerPin ?? state.managerPin,
  );

  void add(Product product, {int qty = 1}) {
    final lines = [...state.lines];
    final index = lines.indexWhere((l) => l.product.id == product.id && !l.hasDiscount);
    if (index >= 0) {
      lines[index] = lines[index].copyWith(qty: lines[index].qty + qty);
    } else {
      lines.add(CartLine(product: product, qty: qty));
    }
    state = _with(lines: lines);
    ref.read(lastAddedProvider.notifier).mark(product.id);
  }

  void setQty(int index, int qty) {
    if (qty < 1) return;
    final lines = [...state.lines]..[index] = state.lines[index].copyWith(qty: qty);
    state = _with(lines: lines);
  }

  void remove(int index) => state = _with(lines: [...state.lines]..removeAt(index));

  void setLineDiscount(int index, DiscountType? type, int value) {
    final line = state.lines[index];
    final lines = [...state.lines]
      ..[index] = type == null ? line.copyWith(clearDiscount: true) : line.copyWith(discountType: type, discountValue: value);
    state = _with(lines: lines);
  }

  void setOrderDiscount(DiscountType? type, int value) =>
      state = type == null ? _with(clearDiscount: true) : _with(discountType: type, discountValue: value);

  void setCustomer(Customer? customer) => state = customer == null ? _with(clearCustomer: true) : _with(customer: customer);

  /// null forgets a PIN the server refused, so the next void asks again.
  void setManagerPin(String? pin) => state = pin == null ? _with(clearManagerPin: true) : _with(managerPin: pin);

  void clear() => state = const Cart();

  /// A held order brought back to the till.
  void restore(Cart cart) => state = cart;
}

final cartProvider = NotifierProvider<CartNotifier, Cart>(CartNotifier.new);

final cartTotalsProvider = Provider<CartTotals>((ref) {
  final cart = ref.watch(cartProvider);
  final settings = ref.watch(sessionProvider.select((s) => s.settings));
  if (cart.isEmpty) return CartTotals.empty;
  return calculate(
    [for (final l in cart.lines) LineInput(l.product.price, l.qty, l.discountType, l.discountValue)],
    orderDiscountType: cart.discountType,
    orderDiscountValue: cart.discountValue,
    taxRateBp: settings.taxRateBp,
    taxInclusive: settings.taxInclusive,
  );
});
