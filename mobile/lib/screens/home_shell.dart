import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../core/theme.dart';
import '../state/sales.dart';
import '../state/session.dart';
import '../widgets/brand_mark.dart';
import 'customers_screen.dart';
import 'more_screen.dart';
import 'pos_screen.dart';
import 'products_screen.dart';
import 'reports_screen.dart';
import 'sales_screen.dart';
import 'settings_screen.dart';
import 'shift_screen.dart';

class _Section {
  const _Section(this.label, this.icon, this.page);
  final String label;
  final IconData icon;
  final Widget page;
}

/// Menu down the left side: always visible on wide screens (web, tablet) and can shrink to icons;
/// in a drawer (☰) on phones.
class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  static const _wideLayout = 800.0;
  static const _shiftIndex = 2;
  int _index = 0;
  bool _collapsed = false;
  Timer? _syncTimer;

  @override
  void initState() {
    super.initState();
    // send offline sales now and every minute
    Future.microtask(_trySync);
    _syncTimer = Timer.periodic(const Duration(minutes: 1), (_) => _trySync());
  }

  Future<void> _trySync() async {
    if (ref.read(offlineQueueProvider).isEmpty) return;
    try {
      await ref.read(offlineQueueProvider.notifier).sync();
    } catch (_) {
      // retried on the next tick
    }
  }

  @override
  void dispose() {
    _syncTimer?.cancel();
    super.dispose();
  }

  List<_Section> _sections(bool isManager) => [
    _Section('POS', Icons.point_of_sale, PosScreen(onOpenShift: () => _select(_shiftIndex))),
    const _Section('Sales', Icons.receipt_long, SalesScreen()),
    const _Section('Shift', Icons.schedule, ShiftScreen()),
    if (isManager) const _Section('Reports', Icons.bar_chart, ReportsScreen()),
    if (isManager) const _Section('Products', Icons.inventory_2, ProductsScreen(embedded: true)),
    const _Section('Customers', Icons.people, CustomersScreen(embedded: true)),
    const _Section('Store settings', Icons.store, SettingsScreen(embedded: true)),
    const _Section('Sync & account', Icons.cloud_sync, MoreScreen()),
  ];

  void _select(int index) {
    setState(() => _index = index);
    if (index == _shiftIndex) ref.invalidate(currentShiftProvider);
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserProvider);
    final sections = _sections(user.isManager);
    final index = _index.clamp(0, sections.length - 1);
    final wide = MediaQuery.sizeOf(context).width >= _wideLayout;
    final collapsed = wide && _collapsed;

    final menu = _Menu(
      sections: sections,
      selected: index,
      collapsed: collapsed,
      onToggle: wide ? () => setState(() => _collapsed = !_collapsed) : null,
      onSelect: (i) {
        _select(i);
        if (!wide) Navigator.of(context).maybePop(); // close the drawer
      },
    );
    final pages = IndexedStack(index: index, children: [for (final s in sections) s.page]);

    final content = Scaffold(
      appBar: AppBar(
        title: Text(sections[index].label),
        automaticallyImplyLeading: !wide,
        actions: [
          _StatusBar(onOpenShift: () => _select(_shiftIndex)),
          const SizedBox(width: 12),
        ],
      ),
      drawer: wide ? null : Drawer(child: menu),
      body: pages,
    );
    // wide: the menu runs the full height on the left, the title bar sits over the content only
    return wide
        ? Row(
            children: [
              AnimatedContainer(duration: const Duration(milliseconds: 180), width: collapsed ? 76 : 248, child: menu),
              Expanded(child: content),
            ],
          )
        : content;
  }
}

/// Exchange rate and cash drawer (shift) status, top right like a till display.
class _StatusBar extends ConsumerWidget {
  const _StatusBar({required this.onOpenShift});

  final VoidCallback onOpenShift;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rate = ref.watch(sessionProvider.select((s) => s.settings.exchangeRate));
    final shift = ref.watch(currentShiftProvider);
    final pending = ref.watch(offlineQueueProvider).length;
    final roomy = MediaQuery.sizeOf(context).width >= 600;
    final open = shift.value != null;

    Widget pill(String text, Color fg, Color bg, {IconData? icon, VoidCallback? onTap}) => Padding(
      padding: const EdgeInsets.only(left: 8),
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon != null) ...[Icon(icon, size: 16, color: fg), const SizedBox(width: 6)],
                Text(
                  text,
                  style: TextStyle(color: fg, fontWeight: FontWeight.w600, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    return Row(
      children: [
        if (pending > 0) pill('$pending to sync', AppColors.warning, AppColors.warningSoft, icon: Icons.cloud_upload),
        if (roomy) pill('1 USD = ${khr(rate)}', AppColors.muted, AppColors.page),
        if (shift.hasValue)
          pill(
            open ? 'Shift open' : 'No shift',
            open ? AppColors.success : AppColors.warning,
            open ? AppColors.successSoft : AppColors.warningSoft,
            icon: open ? Icons.lock_open : Icons.lock_clock,
            onTap: onOpenShift,
          ),
      ],
    );
  }
}

class _Menu extends ConsumerWidget {
  const _Menu({required this.sections, required this.selected, required this.collapsed, required this.onSelect, this.onToggle});

  final List<_Section> sections;
  final int selected;
  final bool collapsed;
  final ValueChanged<int> onSelect;
  final VoidCallback? onToggle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final pending = ref.watch(offlineQueueProvider).length;
    final user = session.user!;

    Widget item(int i) {
      final s = sections[i];
      final isSelected = i == selected;
      final color = isSelected ? AppColors.primary : AppColors.muted;
      final badge = s.page is MoreScreen && pending > 0;
      final icon = Badge(
        isLabelVisible: badge,
        label: Text('$pending'),
        child: Icon(s.icon, color: color),
      );
      return Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Tooltip(
          message: collapsed ? s.label : '',
          child: ListTile(
            dense: true,
            minLeadingWidth: 24,
            contentPadding: const EdgeInsets.symmetric(horizontal: 14),
            leading: icon,
            title: collapsed
                ? null
                : Text(
                    s.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: isSelected ? AppColors.primary : AppColors.text,
                      fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      fontSize: 14,
                    ),
                  ),
            selected: isSelected,
            selectedTileColor: AppColors.primarySoft,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            onTap: () => onSelect(i),
          ),
        ),
      );
    }

    return Material(
      color: Colors.white,
      child: Container(
        decoration: const BoxDecoration(
          border: Border(right: BorderSide(color: AppColors.border)),
        ),
        child: SafeArea(
          right: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: 64,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Row(
                    children: [
                      const BrandMark(size: 40),
                      if (!collapsed) ...[
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            session.settings.storeName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const Divider(),
              Expanded(
                child: ListView(padding: const EdgeInsets.all(12), children: [for (var i = 0; i < sections.length; i++) item(i)]),
              ),
              const Divider(),
              if (collapsed)
                IconButton(
                  tooltip: 'Log out',
                  icon: const Icon(Icons.logout, color: AppColors.muted),
                  onPressed: () => confirmLogout(context, ref),
                )
              else
                ListTile(
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  leading: CircleAvatar(
                    backgroundColor: AppColors.primarySoft,
                    child: Text(
                      user.displayName.characters.first.toUpperCase(),
                      style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700),
                    ),
                  ),
                  title: Text(
                    user.displayName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Text(user.role, style: const TextStyle(color: AppColors.muted)),
                  trailing: IconButton(
                    tooltip: 'Log out',
                    icon: const Icon(Icons.logout, color: AppColors.muted),
                    onPressed: () => confirmLogout(context, ref),
                  ),
                ),
              if (onToggle != null)
                IconButton(
                  tooltip: collapsed ? 'Expand menu' : 'Collapse menu',
                  icon: Icon(collapsed ? Icons.keyboard_double_arrow_right : Icons.keyboard_double_arrow_left, color: AppColors.muted),
                  onPressed: onToggle,
                ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}
