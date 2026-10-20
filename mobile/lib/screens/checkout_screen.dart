import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../models.dart';
import '../state/cart.dart';
import '../state/sales.dart';
import '../state/session.dart';
import '../widgets/common.dart';
import 'receipt_screen.dart';

/// Phone: one column. Wide screens: total and payments on the left, money entry on the right.
class CheckoutScreen extends ConsumerStatefulWidget {
  const CheckoutScreen({super.key});

  @override
  ConsumerState<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends ConsumerState<CheckoutScreen> {
  final _amount = TextEditingController();
  final _payments = <Payment>[];
  String _method = 'cash';
  String _currency = 'USD';
  bool _busy = false;

  int get _rate => ref.read(sessionProvider).settings.exchangeRate;
  int get _total => ref.read(cartTotalsProvider).total;

  int _usdOf(Payment p) => p.currency == 'USD' ? p.amount : khrToUsdCents(p.amount, _rate);
  int get _paid => _payments.fold(0, (sum, p) => sum + _usdOf(p));
  int get _due => _total - _paid;
  bool get _hasKhr => _payments.any((p) => p.currency == 'KHR');

  /// Riel cash is rounded to the 100-riel note, so less than 100 riel short is fine (same rule as the server).
  bool get _canComplete => _payments.isNotEmpty && (_due <= 0 || (_hasKhr && _due * _rate < 100 * 100));

  int? _enteredAmount() => _currency == 'USD' ? parseDollars(_amount.text) : parseWhole(_amount.text);

  bool _add(int amount) {
    if (amount <= 0) return false;
    final usdValue = _currency == 'USD' ? amount : khrToUsdCents(amount, _rate);
    if (_method != 'cash' && usdValue > _due) {
      showMessage(context, 'Card / QR payment cannot be more than the amount due');
      return false;
    }
    setState(() {
      _payments.add(Payment(method: _method, currency: _currency, amount: amount));
      _amount.clear();
    });
    return true;
  }

  /// The amount still due in the selected currency.
  int get _dueInCurrency => _currency == 'USD' ? _due : usdCentsToKhr(_due, _rate);

  List<int> get _quickAmounts => _currency == 'USD'
      ? [100, 500, 1000, 2000, 5000, 10000].where((v) => v >= _due).take(4).toList()
      : [10000, 20000, 50000, 100000].where((v) => v >= _dueInCurrency).take(3).toList();

  /// "Complete" also accepts an amount that was typed but not yet added.
  Future<void> _onComplete() async {
    final typed = _enteredAmount();
    if (typed != null && typed > 0 && !_add(typed)) return;
    if (!_canComplete) {
      showMessage(context, 'Still ${usd(_due)} to pay');
      return;
    }
    await _complete();
  }

  Future<void> _complete() async {
    setState(() => _busy = true);
    try {
      final result = await checkout(ref, List.of(_payments));
      if (!mounted) return;
      switch (result) {
        case SaleCompleted(:final sale):
          await Navigator.pushReplacement(
            context,
            MaterialPageRoute(
              builder: (_) => ReceiptScreen(saleId: sale.id, sale: sale),
            ),
          );
        case SaleQueued(:final pending):
          await showDialog<void>(
            context: context,
            builder: (context) => AlertDialog(
              icon: const Icon(Icons.cloud_off),
              title: const Text('Saved offline'),
              content: Text(
                'The server cannot be reached. This sale (${usd(pending.total)}) is saved on this device '
                'and will be sent automatically when the connection is back.\n\n'
                'Change: ${usd(_paid - pending.total > 0 ? _paid - pending.total : 0)}',
              ),
              actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
            ),
          );
          if (mounted) Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) showError(context, ref, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final totals = ref.watch(cartTotalsProvider);
    final wide = MediaQuery.sizeOf(context).width >= Breakpoints.medium;
    const gap = SizedBox(height: 16);

    final summary = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _TotalCard(total: totals.total, rate: _rate),
        gap,
        _PaymentList(payments: _payments, usdOf: _usdOf, onRemove: (i) => setState(() => _payments.removeAt(i))),
        _Balance(paid: _paid, due: _due, rate: _rate),
      ],
    );
    final entry = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('How is the customer paying?', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'cash', label: Text('Cash'), icon: Icon(Icons.money)),
            ButtonSegment(value: 'card', label: Text('Card'), icon: Icon(Icons.credit_card)),
            ButtonSegment(value: 'khqr', label: Text('KHQR'), icon: Icon(Icons.qr_code)),
          ],
          selected: {_method},
          onSelectionChanged: (s) => setState(() => _method = s.first),
        ),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'USD', label: Text(r'USD $')),
            ButtonSegment(value: 'KHR', label: Text('KHR (riel)')),
          ],
          selected: {_currency},
          onSelectionChanged: (s) => setState(() {
            _currency = s.first;
            _amount.clear();
          }),
        ),
        gap,
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _amount,
                keyboardType: TextInputType.numberWithOptions(decimal: _currency == 'USD'),
                inputFormatters: _currency == 'USD' ? decimalOnly : digitsOnly,
                style: const TextStyle(fontSize: 20),
                decoration: InputDecoration(
                  labelText: _currency == 'USD' ? 'Amount received (USD)' : 'Amount received (riel)',
                  border: const OutlineInputBorder(),
                ),
                onChanged: (_) => setState(() {}),
                onSubmitted: (_) => _add(_enteredAmount() ?? 0),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton.tonal(
              style: FilledButton.styleFrom(minimumSize: const Size(80, 52)),
              onPressed: () => _add(_enteredAmount() ?? 0),
              child: const Text('Add'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (_due > 0)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ActionChip(
                avatar: const Icon(Icons.done_all, size: 18),
                label: Text('Exact ${_currency == 'USD' ? usd(_dueInCurrency) : khr(_dueInCurrency)}'),
                onPressed: () => _add(_dueInCurrency),
              ),
              if (_method == 'cash')
                for (final v in _quickAmounts) ActionChip(label: Text(_currency == 'USD' ? usd(v) : khr(v)), onPressed: () => _add(v)),
            ],
          ),
      ],
    );

    return Scaffold(
      appBar: AppBar(title: const Text('Payment')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: MaxWidth(
          width: wide ? 1100 : 600,
          child: wide
              ? Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: summary),
                    const SizedBox(width: 24),
                    Expanded(child: entry),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _TotalCard(total: totals.total, rate: _rate),
                    gap,
                    entry,
                    gap,
                    _PaymentList(payments: _payments, usdOf: _usdOf, onRemove: (i) => setState(() => _payments.removeAt(i))),
                    _Balance(paid: _paid, due: _due, rate: _rate),
                  ],
                ),
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: MaxWidth(
            width: wide ? 1100 : 600,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (!_canComplete && _amount.text.isEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      'Add the customer\'s payment first: tap "Exact", a quick amount, or type the amount received.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Theme.of(context).colorScheme.outline),
                    ),
                  ),
                FilledButton.icon(
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
                  onPressed: !_busy && (_canComplete || _amount.text.isNotEmpty) ? _onComplete : null,
                  icon: _busy
                      ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.check),
                  label: const Text('Complete sale', style: TextStyle(fontSize: 18)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TotalCard extends StatelessWidget {
  const _TotalCard({required this.total, required this.rate});

  final int total, rate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: theme.colorScheme.primary,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
        child: Column(
          children: [
            const Text('TOTAL', style: TextStyle(color: Colors.white70, letterSpacing: 1)),
            FittedBox(
              child: Text(
                usd(total),
                style: theme.textTheme.displaySmall?.copyWith(color: Colors.white, fontWeight: FontWeight.bold),
              ),
            ),
            Text(khr(usdCentsToKhr(total, rate)), style: theme.textTheme.titleMedium?.copyWith(color: Colors.white)),
            const SizedBox(height: 4),
            Text('1 USD = ${khr(rate)}', style: theme.textTheme.bodySmall?.copyWith(color: Colors.white70)),
          ],
        ),
      ),
    );
  }
}

class _PaymentList extends StatelessWidget {
  const _PaymentList({required this.payments, required this.usdOf, required this.onRemove});

  final List<Payment> payments;
  final int Function(Payment) usdOf;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) {
    if (payments.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Column(
        children: [
          for (var i = 0; i < payments.length; i++)
            ListTile(
              dense: true,
              leading: Icon(switch (payments[i].method) {
                'card' => Icons.credit_card,
                'khqr' => Icons.qr_code,
                _ => Icons.money,
              }),
              title: Text('${payments[i].method.toUpperCase()} ${payments[i].currency}'),
              subtitle: payments[i].currency == 'KHR' ? Text('= ${usd(usdOf(payments[i]))}') : null,
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(payments[i].currency == 'USD' ? usd(payments[i].amount) : khr(payments[i].amount)),
                  IconButton(tooltip: 'Remove', icon: const Icon(Icons.close), onPressed: () => onRemove(i)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Balance extends StatelessWidget {
  const _Balance({required this.paid, required this.due, required this.rate});

  final int paid, due, rate;

  @override
  Widget build(BuildContext context) {
    final error = Theme.of(context).colorScheme.error;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
      child: Column(
        children: [
          MoneyRow('Paid', usd(paid)),
          if (due > 0) ...[
            MoneyRow('Still due', usd(due), bold: true, color: error),
            MoneyRow('Still due (KHR)', khr(usdCentsToKhr(due, rate))),
          ] else ...[
            MoneyRow('Change to give', usd(-due), bold: true, color: Colors.green.shade700),
            MoneyRow('Change (KHR)', khr(usdCentsToKhr(-due, rate))),
          ],
        ],
      ),
    );
  }
}
