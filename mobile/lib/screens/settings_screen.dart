import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../state/session.dart';
import '../widgets/common.dart';

/// Store settings. Everyone can view; only the admin can change them.
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key, this.embedded = false});

  /// Shown inside the main menu, which already has a title bar.
  final bool embedded;

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late final _s = ref.read(sessionProvider).settings;
  late final _name = TextEditingController(text: _s.storeName);
  late final _address = TextEditingController(text: _s.storeAddress);
  late final _phone = TextEditingController(text: _s.storePhone);
  late final _footer = TextEditingController(text: _s.receiptFooter);
  late final _rate = TextEditingController(text: '${_s.exchangeRate}');
  late final _tax = TextEditingController(text: (_s.taxRateBp / 100).toStringAsFixed(2));
  late bool _taxInclusive = _s.taxInclusive;
  late bool _negativeStock = _s.allowNegativeStock;
  bool _busy = false;

  Future<void> _save() async {
    final rate = parseWhole(_rate.text);
    final tax = double.tryParse(_tax.text);
    if (rate == null || rate == 0 || tax == null) {
      showMessage(context, 'Check the exchange rate and VAT');
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(apiProvider).put('/api/settings', {
        'store_name': _name.text.trim(),
        'store_address': _address.text.trim(),
        'store_phone': _phone.text.trim(),
        'receipt_footer': _footer.text.trim(),
        'exchange_rate': rate,
        'tax_rate_bp': (tax * 100).round(),
        'tax_inclusive': _taxInclusive,
        'allow_negative_stock': _negativeStock,
      });
      await ref.read(sessionProvider.notifier).refreshSettings();
      if (mounted) showMessage(context, 'Settings saved');
    } catch (e) {
      if (mounted) showError(context, ref, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final admin = ref.watch(currentUserProvider).isAdmin;
    return Scaffold(
      appBar: widget.embedded ? null : AppBar(title: const Text('Store settings')),
      body: AbsorbPointer(
        absorbing: !admin,
        child: MaxWidth(
          width: 640,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (!admin) const Text('Only the admin can change these settings.'),
              TextField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Store name'),
              ),
              TextField(
                controller: _address,
                decoration: const InputDecoration(labelText: 'Address'),
              ),
              TextField(
                controller: _phone,
                decoration: const InputDecoration(labelText: 'Phone'),
              ),
              TextField(
                controller: _footer,
                decoration: const InputDecoration(labelText: 'Receipt footer'),
              ),
              TextField(
                controller: _rate,
                keyboardType: TextInputType.number,
                inputFormatters: digitsOnly,
                decoration: const InputDecoration(labelText: 'Exchange rate (riel per 1 USD)'),
              ),
              TextField(
                controller: _tax,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: decimalOnly,
                decoration: const InputDecoration(labelText: 'VAT %'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Prices already include VAT'),
                value: _taxInclusive,
                onChanged: (v) => setState(() => _taxInclusive = v),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Allow selling with no stock'),
                value: _negativeStock,
                onChanged: (v) => setState(() => _negativeStock = v),
              ),
              if (admin)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: FilledButton.icon(
                      onPressed: _busy ? null : _save,
                      icon: const Icon(Icons.save),
                      label: const Text('Save settings'),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
