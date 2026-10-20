import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../core/money.dart';
import '../core/pricing.dart';
import '../models.dart';
import '../widgets/common.dart';
import 'cart.dart';
import 'catalog.dart';
import 'session.dart';

/// A sale put on hold ("park" the cart while the customer fetches something). Kept on the server, shared by every
/// till (web and phones); resuming takes it off the list.
class HeldOrder {
  const HeldOrder({
    required this.id,
    required this.label,
    required this.cashierName,
    required this.customerId,
    required this.customerName,
    required this.cart,
    required this.total,
    required this.createdAt,
  });

  factory HeldOrder.fromJson(Json j) => HeldOrder(
    id: j['id'],
    label: j['label'] ?? '',
    cashierName: j['cashier_name'] ?? '',
    customerId: j['customer_id'],
    customerName: j['customer_name'],
    cart: Map<String, dynamic>.from(j['cart']),
    total: j['total'],
    createdAt: DateTime.parse(j['created_at']).toLocal(),
  );

  final int id;
  final String label, cashierName;
  final int? customerId;
  final String? customerName;
  final Map<String, dynamic> cart;
  final int total;
  final DateTime createdAt;

  String get time => '${createdAt.hour.toString().padLeft(2, '0')}:${createdAt.minute.toString().padLeft(2, '0')}';
  String get title => label.isNotEmpty ? label : customerName ?? time;
}

/// Held orders of every till. Offline the list is simply empty.
final heldOrdersProvider = FutureProvider<List<HeldOrder>>((ref) async {
  try {
    final data = await ref.watch(apiProvider).get('/api/parked');
    return [for (final o in data) HeldOrder.fromJson(o)];
  } on ApiException catch (e) {
    if (e.isNetwork) return const [];
    rethrow;
  }
});

Map<String, dynamic> _cartBody(Cart cart) => {
  'items': [
    for (final l in cart.lines)
      {
        'product_id': l.product.id,
        'qty': l.qty,
        if (l.hasDiscount) 'discount_type': l.discountType!.name,
        if (l.hasDiscount) 'discount_value': l.discountValue,
      },
  ],
  if (cart.hasOrderDiscount) 'discount_type': cart.discountType!.name,
  if (cart.hasOrderDiscount) 'discount_value': cart.discountValue,
};

/// Puts the current sale on hold with an optional name, and empties the till for the next customer.
Future<void> holdCart(BuildContext context, WidgetRef ref) async {
  final cart = ref.read(cartProvider);
  if (cart.isEmpty) return;
  final label = await askText(
    context,
    title: 'Hold order',
    label: 'Name or note, so you can find it again (optional)',
    confirmText: 'Hold',
  );
  if (label == null || !context.mounted) return;
  try {
    await ref.read(apiProvider).post('/api/parked', {..._cartBody(cart), 'customer_id': cart.customer?.id, 'label': label.trim()});
    ref.read(cartProvider.notifier).clear();
    if (context.mounted) showMessage(context, 'Order held. Tap it above the cart to continue later.');
  } on ApiException catch (e) {
    if (context.mounted) showMessage(context, e.isNetwork ? 'Holding an order needs the server connection.' : e.message);
  }
  ref.invalidate(heldOrdersProvider);
}

/// Brings a held order back to this till, at today's prices.
Future<void> resumeHeld(BuildContext context, WidgetRef ref, HeldOrder order) async {
  if (!ref.read(cartProvider).isEmpty) {
    showMessage(context, 'Finish or hold the current sale first');
    return;
  }
  final api = ref.read(apiProvider);
  try {
    final taken = HeldOrder.fromJson(await api.post('/api/parked/${order.id}/resume'));
    final products = {for (final p in ref.read(catalogProvider).value?.products ?? <Product>[]) p.id: p};
    final items = [for (final i in taken.cart['items']) Map<String, dynamic>.from(i)];
    final lines = [
      for (final i in items)
        if (products[i['product_id']] != null)
          CartLine(
            product: products[i['product_id']]!,
            qty: i['qty'],
            discountType: i['discount_type'] == null ? null : DiscountType.values.byName(i['discount_type']),
            discountValue: i['discount_value'] ?? 0,
          ),
    ];
    Customer? customer;
    if (taken.customerId != null) {
      try {
        customer = Customer.fromJson(await api.get('/api/customers/${taken.customerId}'));
      } on ApiException {
        customer = null;
      }
    }
    final type = taken.cart['discount_type'] as String?;
    ref
        .read(cartProvider.notifier)
        .restore(
          Cart(
            lines: lines,
            discountType: type == null ? null : DiscountType.values.byName(type),
            discountValue: taken.cart['discount_value'] ?? 0,
            customer: customer,
          ),
        );
    final missing = items.length - lines.length;
    if (missing > 0 && context.mounted) showMessage(context, '$missing item(s) are no longer for sale and were left out');
  } catch (e) {
    if (context.mounted) showError(context, ref, e);
  }
  ref.invalidate(heldOrdersProvider);
}

/// Throwing a held order away is a void: cashiers need a manager PIN, and the server logs it.
Future<void> discardHeld(BuildContext context, WidgetRef ref, HeldOrder order) async {
  if (!await confirm(context, 'Discard held order', 'Throw away the held order of ${usd(order.total)}?', confirmText: 'Discard')) return;
  if (!context.mounted) return;
  String? pin;
  if (!ref.read(currentUserProvider).isManager) {
    pin = await askManagerPin(context, ref, reason: 'Discard held order');
    if (pin == null) return;
  }
  try {
    await ref.read(apiProvider).post('/api/parked/${order.id}/discard', {'manager_pin': pin});
  } catch (e) {
    if (context.mounted) showError(context, ref, e);
  }
  ref.invalidate(heldOrdersProvider);
}
