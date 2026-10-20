import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../models.dart';
import '../state/catalog.dart';
import '../state/sales.dart';
import '../state/session.dart';
import '../widgets/common.dart';
import 'receipt_screen.dart';

class SalesScreen extends ConsumerStatefulWidget {
  const SalesScreen({super.key});

  @override
  ConsumerState<SalesScreen> createState() => _SalesScreenState();
}

class _SalesScreenState extends ConsumerState<SalesScreen> {
  DateTime _day = DateTime.now();
  int? _selectedId;

  Future<void> _pickDay() async {
    final picked = await showDatePicker(context: context, initialDate: _day, firstDate: DateTime(2020), lastDate: DateTime.now());
    if (picked != null) setState(() => _day = picked);
  }

  @override
  Widget build(BuildContext context) {
    final key = isoDate(_day);
    final sales = ref.watch(salesOfDayProvider(key));
    final isToday = key == isoDate(DateTime.now());
    final wide = MediaQuery.sizeOf(context).width >= Breakpoints.wide;

    final list = Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(8),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.chevron_left),
                onPressed: () => setState(() => _day = _day.subtract(const Duration(days: 1))),
              ),
              Expanded(
                child: TextButton.icon(onPressed: _pickDay, icon: const Icon(Icons.calendar_today), label: Text(isToday ? 'Today' : key)),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right),
                onPressed: isToday ? null : () => setState(() => _day = _day.add(const Duration(days: 1))),
              ),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () => ref.refresh(salesOfDayProvider(key).future),
            child: AsyncView<List<SaleSummary>>(
              value: sales,
              onRetry: () => ref.invalidate(salesOfDayProvider(key)),
              builder: (list) {
                if (list.isEmpty) {
                  return ListView(
                    children: const [
                      SizedBox(height: 120),
                      Center(child: Text('No sales on this day')),
                    ],
                  );
                }
                final total = list.fold(0, (sum, s) => sum + s.total - s.refundedTotal);
                return ListView.separated(
                  itemCount: list.length + 1,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    if (i == 0) {
                      return ListTile(
                        title: Text('${list.length} sale(s)', style: const TextStyle(fontWeight: FontWeight.bold)),
                        trailing: Text(usd(total), style: Theme.of(context).textTheme.titleMedium),
                      );
                    }
                    final sale = list[i - 1];
                    return ListTile(
                      title: Text(sale.receiptNo),
                      subtitle: Text(
                        [
                          dateTime(sale.createdAt).substring(11),
                          sale.cashierName,
                          if (sale.customerName != null) sale.customerName!,
                        ].join(' • '),
                      ),
                      trailing: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(usd(sale.total), style: const TextStyle(fontWeight: FontWeight.bold)),
                          if (sale.status != 'completed')
                            Text(
                              sale.status.replaceAll('_', ' '),
                              style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 12),
                            ),
                        ],
                      ),
                      selected: wide && sale.id == _selectedId,
                      selectedTileColor: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.5),
                      onTap: () => wide
                          ? setState(() => _selectedId = sale.id)
                          : Navigator.push(context, MaterialPageRoute(builder: (_) => SaleDetailScreen(saleId: sale.id))),
                    );
                  },
                );
              },
            ),
          ),
        ),
      ],
    );

    if (!wide) return list;
    return Row(
      children: [
        SizedBox(width: 420, child: list),
        const VerticalDivider(width: 1),
        Expanded(
          child: _selectedId == null
              ? const Center(child: Text('Select a sale to see its details'))
              : SaleDetailView(key: ValueKey(_selectedId), saleId: _selectedId!),
        ),
      ],
    );
  }
}

class SaleDetailScreen extends ConsumerWidget {
  const SaleDetailScreen({super.key, required this.saleId});

  final int saleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sale = ref.watch(saleProvider(saleId));
    return Scaffold(
      appBar: AppBar(title: Text(sale.value?.receiptNo ?? 'Sale')),
      body: SaleDetailView(saleId: saleId),
    );
  }
}

/// Items, totals, receipt and refund for one sale. Used full screen on phones, as a side panel on wide screens.
class SaleDetailView extends ConsumerWidget {
  const SaleDetailView({super.key, required this.saleId});

  final int saleId;

  Future<void> _refund(BuildContext context, WidgetRef ref, Sale sale) async {
    final request = await showDialog<_RefundRequest>(
      context: context,
      builder: (_) => _RefundDialog(sale: sale),
    );
    if (request == null || !context.mounted) return;

    String? pin;
    if (!ref.read(currentUserProvider).isManager) {
      pin = await askManagerPin(context, ref, reason: 'Approve refund');
      if (pin == null) return;
    }
    try {
      final result = await ref.read(apiProvider).post('/api/sales/${sale.id}/refund', {
        'items': [
          for (final e in request.qty.entries)
            if (e.value > 0) {'sale_item_id': e.key, 'qty': e.value},
        ],
        'reason': request.reason,
        'manager_pin': pin,
      });
      ref.invalidate(saleProvider(sale.id));
      ref.invalidate(salesOfDayProvider);
      ref.invalidate(currentShiftProvider);
      ref.invalidate(catalogProvider);
      if (context.mounted) showMessage(context, 'Refunded ${usd(result['amount'])}. Give the money back to the customer.');
    } catch (e) {
      if (context.mounted) showError(context, ref, e);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sale = ref.watch(saleProvider(saleId));
    return AsyncView<Sale>(
      value: sale,
      onRetry: () => ref.invalidate(saleProvider(saleId)),
      builder: (s) => MaxWidth(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(s.receiptNo, style: Theme.of(context).textTheme.titleLarge),
            Text('${dateTime(s.createdAt)} • ${s.cashierName}${s.customerName == null ? '' : ' • ${s.customerName}'}'),
            if (s.status != 'completed')
              Text(s.status.replaceAll('_', ' ').toUpperCase(), style: TextStyle(color: Theme.of(context).colorScheme.error)),
            const Divider(),
            for (final item in s.items)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(item.productName),
                subtitle: Text(
                  [
                    '${item.qty} x ${usd(item.unitPrice)}',
                    if (item.discount > 0) 'disc. -${usd(item.discount)}',
                    if (item.refundedQty > 0) 'refunded ${item.refundedQty}',
                  ].join('  '),
                ),
                trailing: Text(usd(item.lineTotal)),
              ),
            const Divider(),
            MoneyRow('Subtotal', usd(s.subtotal)),
            if (s.discountTotal > 0) MoneyRow('Discount', '-${usd(s.discountTotal)}'),
            if (s.taxTotal > 0) MoneyRow('VAT', usd(s.taxTotal)),
            MoneyRow('Total', usd(s.total), bold: true),
            for (final p in s.payments)
              MoneyRow('${p.method.toUpperCase()} ${p.currency}', p.currency == 'USD' ? usd(p.amount) : khr(p.amount)),
            if (s.changeDue > 0) MoneyRow('Change', usd(s.changeDue)),
            if (s.refundedTotal > 0) MoneyRow('Refunded', '-${usd(s.refundedTotal)}', color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReceiptScreen(saleId: s.id))),
                    icon: const Icon(Icons.receipt_long),
                    label: const Text('Receipt'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: s.canRefund ? () => _refund(context, ref, s) : null,
                    icon: const Icon(Icons.undo),
                    label: const Text('Refund'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RefundRequest {
  const _RefundRequest(this.qty, this.reason);
  final Map<int, int> qty;
  final String reason;
}

class _RefundDialog extends StatefulWidget {
  const _RefundDialog({required this.sale});
  final Sale sale;

  @override
  State<_RefundDialog> createState() => _RefundDialogState();
}

class _RefundDialogState extends State<_RefundDialog> {
  late final Map<int, int> _qty = {for (final i in widget.sale.items) i.id: i.refundableQty};
  final _reason = TextEditingController();

  @override
  Widget build(BuildContext context) {
    final refundable = widget.sale.items.where((i) => i.refundableQty > 0);
    final valid = _reason.text.trim().isNotEmpty && _qty.values.any((q) => q > 0);
    return AlertDialog(
      title: const Text('Refund items'),
      content: SizedBox(
        width: 400,
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final item in refundable)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(item.productName),
                subtitle: Text('max ${item.refundableQty}'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.remove),
                      onPressed: _qty[item.id]! > 0 ? () => setState(() => _qty[item.id] = _qty[item.id]! - 1) : null,
                    ),
                    Text('${_qty[item.id]}'),
                    IconButton(
                      icon: const Icon(Icons.add),
                      onPressed: _qty[item.id]! < item.refundableQty ? () => setState(() => _qty[item.id] = _qty[item.id]! + 1) : null,
                    ),
                  ],
                ),
              ),
            TextField(
              controller: _reason,
              decoration: const InputDecoration(labelText: 'Reason (required)'),
              onChanged: (_) => setState(() {}),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: valid ? () => Navigator.pop(context, _RefundRequest(_qty, _reason.text.trim())) : null,
          child: const Text('Refund'),
        ),
      ],
    );
  }
}
