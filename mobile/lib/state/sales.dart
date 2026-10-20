import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../api/api_client.dart';
import '../models.dart';
import 'cart.dart';
import 'catalog.dart';
import 'session.dart';

/// A sale made while the server was unreachable, waiting to be sent.
class PendingSale {
  const PendingSale({required this.uuid, required this.payload, required this.total, required this.createdAt, this.error});

  factory PendingSale.fromJson(Json j) =>
      PendingSale(uuid: j['uuid'], payload: j['payload'], total: j['total'], createdAt: DateTime.parse(j['created_at']), error: j['error']);

  final String uuid;
  final Json payload;
  final int total;
  final DateTime createdAt;

  /// Set when the server rejected the sale (e.g. wrong manager PIN); it then needs a manager.
  final String? error;

  Json toJson() => {'uuid': uuid, 'payload': payload, 'total': total, 'created_at': createdAt.toIso8601String(), 'error': error};

  PendingSale withError(String message) => PendingSale(uuid: uuid, payload: payload, total: total, createdAt: createdAt, error: message);
}

class OfflineQueue extends Notifier<List<PendingSale>> {
  static const _key = 'pending_sales';

  @override
  List<PendingSale> build() {
    final raw = ref.read(prefsProvider).getString(_key);
    if (raw == null) return [];
    return [for (final j in jsonDecode(raw)) PendingSale.fromJson(j)];
  }

  Future<void> _save(List<PendingSale> sales) async {
    state = sales;
    await ref.read(prefsProvider).setString(_key, jsonEncode([for (final s in sales) s.toJson()]));
  }

  Future<void> add(PendingSale sale) => _save([...state, sale]);

  Future<void> discard(String uuid) => _save([
    for (final s in state)
      if (s.uuid != uuid) s,
  ]);

  /// Sends waiting sales. The server ignores duplicates (same client_uuid), so retrying is safe.
  Future<int> sync() async {
    final api = ref.read(apiProvider);
    var sent = 0;
    for (final sale in [...state]) {
      if (sale.error != null) continue;
      try {
        await api.post('/api/sales', sale.payload);
        await _save([
          for (final s in state)
            if (s.uuid != sale.uuid) s,
        ]);
        sent++;
      } on ApiException catch (e) {
        if (e.isNetwork || e.isUnauthorized) break;
        await _save([for (final s in state) s.uuid == sale.uuid ? s.withError(e.message) : s]);
      }
    }
    if (sent > 0) ref.invalidate(catalogProvider);
    return sent;
  }
}

final offlineQueueProvider = NotifierProvider<OfflineQueue, List<PendingSale>>(OfflineQueue.new);

/// Either a saved sale, or one queued on the phone because the server was unreachable.
sealed class CheckoutResult {}

class SaleCompleted extends CheckoutResult {
  SaleCompleted(this.sale);
  final Sale sale;
}

class SaleQueued extends CheckoutResult {
  SaleQueued(this.pending);
  final PendingSale pending;
}

Future<CheckoutResult> checkout(WidgetRef ref, List<Payment> payments) async {
  final cart = ref.read(cartProvider);
  final total = ref.read(cartTotalsProvider).total;
  final rate = ref.read(sessionProvider).settings.exchangeRate;
  final uuid = const Uuid().v4();
  final payload = <String, dynamic>{
    'items': [
      for (final l in cart.lines)
        {
          'product_id': l.product.id,
          'qty': l.qty,
          'unit_price': l.product.price, // the price the customer saw; kept if this sale has to wait offline
          if (l.hasDiscount) 'discount_type': l.discountType!.name,
          if (l.hasDiscount) 'discount_value': l.discountValue,
        },
    ],
    if (cart.hasOrderDiscount) 'discount_type': cart.discountType!.name,
    if (cart.hasOrderDiscount) 'discount_value': cart.discountValue,
    'payments': [for (final p in payments) p.toJson()],
    'customer_id': cart.customer?.id,
    'manager_pin': cart.managerPin,
    'client_uuid': uuid,
    'created_at': DateTime.now().toIso8601String(),
    'exchange_rate': rate,
  };

  try {
    final sale = Sale.fromJson(await ref.read(apiProvider).post('/api/sales', payload));
    ref.read(cartProvider.notifier).clear();
    ref.invalidate(catalogProvider);
    return SaleCompleted(sale);
  } on ApiException catch (e) {
    if (!e.isNetwork) rethrow;
    // The customer has paid and left: when it syncs, the server keeps these prices and never refuses it.
    payload['offline'] = true;
    final pending = PendingSale(uuid: uuid, payload: payload, total: total, createdAt: DateTime.now());
    await ref.read(offlineQueueProvider.notifier).add(pending);
    ref.read(cartProvider.notifier).clear();
    return SaleQueued(pending);
  }
}

final currentShiftProvider = FutureProvider<ShiftReport?>((ref) async {
  final data = await ref.watch(apiProvider).get('/api/shifts/current');
  return data == null ? null : ShiftReport.fromJson(data);
});

final salesOfDayProvider = FutureProvider.family<List<SaleSummary>, String>((ref, day) async {
  final data = await ref.watch(apiProvider).get('/api/sales', query: {'date_from': day, 'date_to': day});
  return [for (final s in data) SaleSummary.fromJson(s)];
});

final saleProvider = FutureProvider.family<Sale, int>((ref, id) async {
  return Sale.fromJson(await ref.watch(apiProvider).get('/api/sales/$id'));
});
