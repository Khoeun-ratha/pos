import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../models.dart';
import '../state/sales.dart';
import '../state/session.dart';
import '../widgets/common.dart';

class ShiftScreen extends ConsumerStatefulWidget {
  const ShiftScreen({super.key});

  @override
  ConsumerState<ShiftScreen> createState() => _ShiftScreenState();
}

class _ShiftScreenState extends ConsumerState<ShiftScreen> {
  final _openingCash = TextEditingController(text: '0');
  bool _busy = false;

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) showError(context, ref, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _open() => _run(() async {
    final cents = parseDollars(_openingCash.text);
    if (cents == null) return;
    await ref.read(apiProvider).post('/api/shifts/open', {'opening_cash': cents});
    ref.invalidate(currentShiftProvider);
  });

  Future<void> _cashMovement(bool cashIn) async {
    final amount = await askText(
      context,
      title: cashIn ? 'Cash in' : 'Cash out',
      label: 'Amount (USD)',
      keyboard: const TextInputType.numberWithOptions(decimal: true),
    );
    final cents = amount == null ? null : parseDollars(amount);
    if (cents == null || cents == 0 || !mounted) return;
    final reason = await askText(context, title: 'Reason', label: cashIn ? 'e.g. Add small change' : 'e.g. Buy ice');
    if (reason == null || reason.trim().isEmpty) return;
    await _run(() async {
      await ref.read(apiProvider).post('/api/shifts/current/cash', {'amount': cashIn ? cents : -cents, 'reason': reason.trim()});
      ref.invalidate(currentShiftProvider);
    });
  }

  Future<void> _close(ShiftReport shift) async {
    final counted = await showDialog<(int, int)>(context: context, builder: (_) => const _CountCashDialog());
    if (counted == null) return;
    await _run(() async {
      final data = await ref.read(apiProvider).post('/api/shifts/current/close', {'counted_usd': counted.$1, 'counted_khr': counted.$2});
      final report = ShiftReport.fromJson(data);
      ref.invalidate(currentShiftProvider);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Shift closed'),
          content: SingleChildScrollView(child: ShiftReportView(report: report)),
          actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final shift = ref.watch(currentShiftProvider);
    return RefreshIndicator(
      onRefresh: () => ref.refresh(currentShiftProvider.future),
      child: AsyncView<ShiftReport?>(
        value: shift,
        onRetry: () => ref.invalidate(currentShiftProvider),
        builder: (report) => MaxWidth(
          width: 600,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (report == null) ...[
                Text('No open shift', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 8),
                const Text('Count the cash in the drawer and enter it to start your shift.'),
                const SizedBox(height: 16),
                TextField(
                  controller: _openingCash,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: decimalOnly,
                  decoration: const InputDecoration(labelText: 'Opening cash (USD)', border: OutlineInputBorder(), prefixText: r'$ '),
                ),
                const SizedBox(height: 16),
                FilledButton.icon(
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                  onPressed: _busy ? null : _open,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Open shift'),
                ),
              ] else ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: ShiftReportView(report: report),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _busy ? null : () => _cashMovement(true),
                        icon: const Icon(Icons.add),
                        label: const Text('Cash in'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _busy ? null : () => _cashMovement(false),
                        icon: const Icon(Icons.remove),
                        label: const Text('Cash out'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                  onPressed: _busy ? null : () => _close(report),
                  icon: const Icon(Icons.lock_clock),
                  label: const Text('Close shift'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class ShiftReportView extends StatelessWidget {
  const ShiftReportView({super.key, required this.report});

  final ShiftReport report;

  @override
  Widget build(BuildContext context) {
    final variance = report.variance;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(report.cashierName, style: Theme.of(context).textTheme.titleLarge),
        Text('Opened ${dateTime(report.openedAt)}${report.closedAt == null ? '' : '\nClosed ${dateTime(report.closedAt!)}'}'),
        const Divider(),
        MoneyRow('Sales', '${report.salesCount}'),
        MoneyRow('Opening cash', usd(report.openingCash)),
        MoneyRow('Cash sales', usd(report.cashSales)),
        MoneyRow('Cash in', usd(report.cashIn)),
        MoneyRow('Cash out', '-${usd(report.cashOut)}'),
        MoneyRow('Cash refunds', '-${usd(report.cashRefunds)}'),
        MoneyRow('Expected in drawer', usd(report.expectedCash), bold: true),
        if (report.countedCash != null) MoneyRow('Counted', usd(report.countedCash!), bold: true),
        if (variance != null)
          MoneyRow(
            variance == 0 ? 'Balanced' : (variance > 0 ? 'Over' : 'Short'),
            usd(variance.abs()),
            bold: true,
            color: variance == 0 ? Colors.green : Theme.of(context).colorScheme.error,
          ),
        const Divider(),
        MoneyRow('Card sales', usd(report.cardSales)),
        MoneyRow('KHQR sales', usd(report.khqrSales)),
      ],
    );
  }
}

class _CountCashDialog extends StatefulWidget {
  const _CountCashDialog();

  @override
  State<_CountCashDialog> createState() => _CountCashDialogState();
}

class _CountCashDialogState extends State<_CountCashDialog> {
  final _usd = TextEditingController();
  final _khr = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Count the drawer'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _usd,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: decimalOnly,
            decoration: const InputDecoration(labelText: 'US dollars counted', prefixText: r'$ '),
          ),
          TextField(
            controller: _khr,
            keyboardType: TextInputType.number,
            inputFormatters: digitsOnly,
            decoration: const InputDecoration(labelText: 'Riel counted', suffixText: 'KHR'),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () => Navigator.pop(context, (
            parseDollars(_usd.text.isEmpty ? '0' : _usd.text) ?? 0,
            parseWhole(_khr.text.isEmpty ? '0' : _khr.text) ?? 0,
          )),
          child: const Text('Close shift'),
        ),
      ],
    );
  }
}
