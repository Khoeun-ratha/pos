import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../models.dart';
import '../state/session.dart';
import '../widgets/common.dart';

final reportProvider = FutureProvider.autoDispose.family<ReportSummary, int>((ref, days) async {
  final today = DateTime.now();
  final from = today.subtract(Duration(days: days - 1));
  final data = await ref.watch(apiProvider).get('/api/reports/summary', query: {'date_from': isoDate(from), 'date_to': isoDate(today)});
  return ReportSummary.fromJson(data);
});

final lowStockProvider = FutureProvider.autoDispose<List<Product>>((ref) async {
  final data = await ref.watch(apiProvider).get('/api/inventory/low-stock');
  return [for (final p in data) Product.fromJson(p)];
});

class ReportsScreen extends ConsumerStatefulWidget {
  const ReportsScreen({super.key});

  @override
  ConsumerState<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends ConsumerState<ReportsScreen> {
  int _days = 1;

  @override
  Widget build(BuildContext context) {
    final report = ref.watch(reportProvider(_days));
    return RefreshIndicator(
      onRefresh: () {
        ref.invalidate(lowStockProvider);
        return ref.refresh(reportProvider(_days).future);
      },
      child: MaxWidth(
        width: 1200,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 1, label: Text('Today')),
                ButtonSegment(value: 7, label: Text('7 days')),
                ButtonSegment(value: 30, label: Text('30 days')),
              ],
              selected: {_days},
              onSelectionChanged: (s) => setState(() => _days = s.first),
            ),
            const SizedBox(height: 16),
            AsyncView<ReportSummary>(
              value: report,
              onRetry: () => ref.invalidate(reportProvider(_days)),
              builder: (r) => _ReportBody(report: r),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReportBody extends StatelessWidget {
  const _ReportBody({required this.report});

  final ReportSummary report;

  @override
  Widget build(BuildContext context) {
    final r = report;
    final stats = [
      _Stat('Net sales', usd(r.netSales), Icons.attach_money),
      _Stat('Sales', '${r.salesCount}', Icons.receipt),
      _Stat('Profit', usd(r.profit), Icons.trending_up),
      _Stat('Average sale', usd(r.averageSale), Icons.functions),
      _Stat('Gross sales', usd(r.grossSales), Icons.payments),
      _Stat('Refunds', usd(r.refunds), Icons.undo),
      _Stat('Discounts', usd(r.discounts), Icons.percent),
      _Stat('VAT collected', usd(r.tax), Icons.account_balance),
    ];
    final left = [
      _Section('Top products', child: _AmountList(rows: r.topProducts, showQty: true)),
      _Section('Categories', child: _AmountList(rows: r.byCategory, showQty: true)),
    ];
    final right = [_Section('Payment methods', child: _AmountList(rows: r.byPayment, showCount: true)), const _LowStockCard()];

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        // 2 stat cards per row on phones, 4 on wide screens
        final perRow = width >= 900 ? 4 : (width >= 560 ? 3 : 2);
        final statWidth = (width - 12 * (perRow - 1)) / perRow;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [for (final s in stats) SizedBox(width: statWidth, child: s)],
            ),
            if (r.byDay.length > 1)
              _Section(
                'Sales by day',
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(8, 16, 8, 8),
                    child: SizedBox(height: 220, child: _DailyChart(days: r.byDay)),
                  ),
                ),
              ),
            if (width >= 900)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: left),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: right),
                  ),
                ],
              )
            else ...[
              ...left,
              ...right,
            ],
          ],
        );
      },
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value, this.icon);

  final String label, value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 4),
              Text(label, style: Theme.of(context).textTheme.bodySmall),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section(this.title, {required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}

class _AmountList extends StatelessWidget {
  const _AmountList({required this.rows, this.showQty = false, this.showCount = false});

  final List<NameAmount> rows;
  final bool showQty, showCount;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const Text('No data');
    return Card(
      child: Column(
        children: [
          for (final row in rows)
            ListTile(
              dense: true,
              title: Text(row.name),
              subtitle: showQty ? Text('${row.qty} sold') : (showCount ? Text('${row.count} payment(s)') : null),
              trailing: Text(usd(row.amount), style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
        ],
      ),
    );
  }
}

class _DailyChart extends StatelessWidget {
  const _DailyChart({required this.days});

  final List<({DateTime day, int amount})> days;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    final labelEvery = (days.length / 7).ceil();
    return BarChart(
      BarChartData(
        gridData: const FlGridData(show: false),
        borderData: FlBorderData(show: false),
        barTouchData: BarTouchData(
          touchTooltipData: BarTouchTooltipData(
            getTooltipItem: (group, _, rod, _) => BarTooltipItem(
              '${isoDate(days[group.x].day)}\n${usd(rod.toY.round())}',
              const TextStyle(color: Colors.white, fontSize: 12),
            ),
          ),
        ),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(),
          rightTitles: const AxisTitles(),
          leftTitles: const AxisTitles(),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                final i = value.toInt();
                if (i % labelEvery != 0 || i >= days.length) return const SizedBox.shrink();
                return Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('${days[i].day.day}/${days[i].day.month}', style: const TextStyle(fontSize: 10)),
                );
              },
            ),
          ),
        ),
        barGroups: [
          for (var i = 0; i < days.length; i++)
            BarChartGroupData(
              x: i,
              barRods: [
                BarChartRodData(
                  toY: days[i].amount.toDouble(),
                  color: color,
                  width: days.length > 14 ? 6 : 14,
                  borderRadius: BorderRadius.circular(3),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _LowStockCard extends ConsumerWidget {
  const _LowStockCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lowStock = ref.watch(lowStockProvider);
    return _Section(
      'Low stock',
      child: AsyncView<List<Product>>(
        value: lowStock,
        onRetry: () => ref.invalidate(lowStockProvider),
        builder: (products) => products.isEmpty
            ? const Text('All products have enough stock')
            : Card(
                child: Column(
                  children: [
                    for (final p in products)
                      ListTile(
                        dense: true,
                        leading: Icon(Icons.warning_amber, color: Theme.of(context).colorScheme.error),
                        title: Text(p.name),
                        trailing: Text('${p.stockQty} left', style: TextStyle(color: Theme.of(context).colorScheme.error)),
                      ),
                  ],
                ),
              ),
      ),
    );
  }
}
