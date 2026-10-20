import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../core/money.dart';
import '../models.dart';
import '../state/scan.dart';
import '../state/session.dart';
import '../widgets/common.dart';

/// 58mm printers fit 32 characters per line. A receipt opened later is a reprint: marked as a copy and logged.
final receiptTextProvider = FutureProvider.autoDispose.family<String, (int, bool)>((ref, key) {
  final (saleId, reprint) = key;
  return ref.watch(apiProvider).getText('/api/sales/$saleId/receipt', query: {'width': '32', if (reprint) 'reprint': 'true'});
});

class ReceiptScreen extends ConsumerWidget {
  const ReceiptScreen({super.key, required this.saleId, this.sale});

  final int saleId;

  /// Set right after a sale, to show the change in large type.
  final Sale? sale;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final text = ref.watch(receiptTextProvider((saleId, sale == null)));
    final theme = Theme.of(context);
    // right after a sale, scanning the next customer's first item closes the receipt and starts the next sale
    return ScanListener(
      onScan: (code) {
        if (sale == null) return;
        Navigator.pop(context);
        ref.read(scanRequestProvider.notifier).send(code);
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(sale?.receiptNo ?? 'Receipt'),
          actions: [
            if (text.hasValue) ...[
              IconButton(
                tooltip: 'Copy',
                icon: const Icon(Icons.copy),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: text.value!));
                  showMessage(context, 'Receipt copied');
                },
              ),
              IconButton(
                tooltip: 'Share',
                icon: const Icon(Icons.share),
                onPressed: () => SharePlus.instance.share(ShareParams(text: text.value!, subject: 'Receipt')),
              ),
            ],
          ],
        ),
        body: MaxWidth(
          width: 480,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (sale != null && sale!.changeDue > 0)
                Card(
                  color: Colors.green.shade100,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        const Text('Change', style: TextStyle(color: Colors.black87)),
                        Text(
                          usd(sale!.changeDue),
                          style: theme.textTheme.displaySmall?.copyWith(color: Colors.black, fontWeight: FontWeight.bold),
                        ),
                        Text(khr(sale!.changeDueKhr), style: theme.textTheme.titleMedium?.copyWith(color: Colors.black87)),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 8),
              Center(
                child: Container(
                  padding: const EdgeInsets.all(16),
                  color: Colors.white,
                  child: AsyncView<String>(
                    value: text,
                    onRetry: () => ref.invalidate(receiptTextProvider((saleId, sale == null))),
                    builder: (receipt) => Text(
                      receipt,
                      style: const TextStyle(fontFamily: 'monospace', fontSize: 13, color: Colors.black, height: 1.3),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        bottomNavigationBar: sale == null
            ? null
            : SafeArea(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: MaxWidth(
                    width: 480,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.add_shopping_cart),
                      label: const Text('New sale', style: TextStyle(fontSize: 18)),
                    ),
                  ),
                ),
              ),
      ),
    );
  }
}
