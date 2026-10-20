import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../core/money.dart';
import '../core/theme.dart';
import '../models.dart';
import '../state/cart.dart';
import '../state/catalog.dart';
import '../state/held.dart';
import '../state/sales.dart';
import '../state/scan.dart';
import '../state/session.dart';
import '../widgets/cart_panel.dart';
import '../widgets/common.dart';
import '../widgets/product_image.dart';
import 'products_screen.dart';
import 'scanner_screen.dart';

class PosScreen extends ConsumerStatefulWidget {
  const PosScreen({super.key, required this.onOpenShift});

  final VoidCallback onOpenShift;

  @override
  ConsumerState<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends ConsumerState<PosScreen> {
  final _search = TextEditingController();
  final _searchFocus = FocusNode();
  int? _categoryId;
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  void _clearSearch() {
    _search.clear();
    setState(() => _query = '');
  }

  int _inCart(Product product) => ref.read(cartProvider).lines.where((l) => l.product.id == product.id).fold(0, (n, l) => n + l.qty);

  /// Adds the product ("3*" typed in front adds 3) and clears the search box. Returns a stock warning, if any.
  String? _add(Product product, {int? qty}) {
    ref.read(cartProvider.notifier).add(product, qty: qty ?? splitQty(_search.text).$1);
    scanFeedback(ref, ok: true);
    _clearSearch();
    if (product.trackStock && _inCart(product) > product.stockQty) return 'only ${product.stockQty < 0 ? 0 : product.stockQty} in stock';
    return null;
  }

  void _addAndTell(Product product, {int? qty}) {
    final warning = _add(product, qty: qty);
    if (warning != null) showMessage(context, '${product.name}: $warning');
  }

  /// The product with this barcode / SKU. Products added since the list was loaded are asked from the server.
  Future<Product?> _lookup(String code) async {
    final catalog = ref.read(catalogProvider).value;
    final known = catalog?.byCode(code);
    if (known != null || catalog == null || catalog.fromCache) return known;
    try {
      return Product.fromJson(await ref.read(apiProvider).get('/api/products/barcode/${Uri.encodeComponent(cleanCode(code))}'));
    } on ApiException catch (e) {
      if (e.status == 404 || e.isNetwork) return null;
      rethrow;
    }
  }

  /// A scanned or typed barcode / SKU.
  Future<void> _addByCode(String code, {int? qty}) async {
    final count = qty ?? splitQty(_search.text).$1;
    Product? product;
    try {
      product = await _lookup(code);
    } catch (e) {
      scanFeedback(ref, ok: false);
      if (mounted) showError(context, ref, e);
      return;
    }
    if (!mounted) return;
    if (product != null) return _addAndTell(product, qty: count);
    await _unknown(cleanCode(code));
  }

  /// A manager can create the product on the spot (the barcode is filled in); a cashier is told to ask one.
  Future<void> _unknown(String code) async {
    scanFeedback(ref, ok: false);
    _clearSearch();
    if (!ref.read(currentUserProvider).isManager) {
      showMessage(context, 'No product with barcode $code. Ask a manager to add it.');
      return;
    }
    final create = await confirm(context, 'Unknown barcode', 'No product has barcode $code. Add it as a new product?', confirmText: 'New product');
    if (!create) return;
    if (!mounted) return;
    final saved = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => ProductEditScreen(barcode: code)));
    if (saved != true || !mounted) return;
    ref.invalidate(allProductsProvider);
    await ref.read(catalogProvider.notifier).refresh();
    final product = ref.read(catalogProvider).value?.byCode(code);
    if (product != null && mounted) _addAndTell(product, qty: 1);
  }

  /// Camera scanning stays open: every item is added as it is scanned, until the cashier taps Done.
  Future<void> _scan() => ScannerScreen.scanMany(context, (code) async {
    try {
      final product = await _lookup(code);
      if (product == null) return (ok: false, message: 'No product with barcode ${cleanCode(code)}');
      final warning = _add(product);
      return (
        ok: true,
        message: '${product.name} · ${usd(product.price)} · ${_inCart(product)} in cart${warning == null ? '' : ' ($warning)'}',
      );
    } catch (e) {
      return (ok: false, message: '$e');
    }
  });

  /// Enter in the search box: a barcode / SKU, or the only product whose name matches the words typed.
  void _onSubmitted(String text) {
    final (qty, rest) = splitQty(text);
    if (rest.isEmpty) return;
    final catalog = ref.read(catalogProvider).value;
    var product = catalog?.byCode(rest);
    var matches = 0;
    if (product == null && catalog != null) {
      final words = rest.toLowerCase();
      final found = catalog.products.where((p) => p.name.toLowerCase().contains(words)).take(2).toList();
      matches = found.length;
      if (found.length == 1) product = found.first;
    }
    if (product != null) {
      _addAndTell(product, qty: qty);
    } else if (matches > 1) {
      showMessage(context, 'Several products match. Tap the one you want.');
    } else if (RegExp(r'^[0-9A-Za-z-]{4,}$').hasMatch(cleanCode(rest))) {
      _addByCode(rest, qty: qty);
    } else {
      scanFeedback(ref, ok: false);
      showMessage(context, 'No product matches "$rest"');
    }
    _searchFocus.requestFocus(); // ready for the next scan from a USB / Bluetooth scanner
  }

  @override
  Widget build(BuildContext context) {
    final catalog = ref.watch(catalogProvider);
    final sound = ref.watch(scanSoundProvider);
    // a scan made while the receipt of the last sale was showing
    ref.listen(scanRequestProvider, (_, request) {
      if (request != null) _addByCode(request.$1, qty: 1);
    });
    final pending = isPendingQty(_search.text) ? splitQty(_search.text).$1 : null;

    return ScanListener(
      onScan: (code) => _addByCode(code),
      shortcuts: {
        LogicalKeyboardKey.f2: () => _searchFocus.requestFocus(),
        LogicalKeyboardKey.f4: () => holdCart(context, ref),
        LogicalKeyboardKey.f12: () => startCheckout(context, ref),
        LogicalKeyboardKey.escape: () => _search.text.isEmpty ? null : _clearSearch(),
      },
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth >= 860;
          final products = Column(
            children: [
              _ShiftBanner(onOpenShift: widget.onOpenShift),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: TextField(
                  controller: _search,
                  focusNode: _searchFocus,
                  style: const TextStyle(fontSize: 16),
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: wide ? 'Search or scan a barcode... (F2)' : 'Search or scan a barcode...',
                    prefixIcon: Icon(
                      pending != null ? Icons.qr_code_2 : Icons.search,
                      color: pending != null ? AppColors.primary : AppColors.muted,
                    ),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                    helperText: pending != null
                        ? 'Next scan or tap adds $pending'
                        : wide
                        ? 'F2 search · 3* quantity, then scan · F4 hold · F12 pay'
                        : null,
                    helperStyle: TextStyle(
                      color: pending != null ? AppColors.primary : AppColors.muted,
                      fontWeight: pending != null ? FontWeight.w600 : null,
                    ),
                    suffixIcon: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_query.isNotEmpty || pending != null)
                          IconButton(tooltip: 'Clear search', icon: const Icon(Icons.close), onPressed: _clearSearch),
                        IconButton(
                          tooltip: sound ? 'Scanner sound on' : 'Scanner sound off',
                          icon: Icon(sound ? Icons.volume_up_outlined : Icons.volume_off_outlined, color: AppColors.muted),
                          onPressed: () => ref.read(scanSoundProvider.notifier).set(!sound),
                        ),
                        IconButton(
                          tooltip: 'Scan with camera',
                          icon: const Icon(Icons.qr_code_scanner, color: AppColors.primary),
                          onPressed: _scan,
                        ),
                        const SizedBox(width: 4),
                      ],
                    ),
                  ),
                  onChanged: (_) => setState(() => _query = splitQty(_search.text).$2.toLowerCase()),
                  onSubmitted: _onSubmitted,
                ),
              ),
              Expanded(
                child: AsyncView<Catalog>(
                  value: catalog,
                  onRetry: () => ref.invalidate(catalogProvider),
                  builder: (data) => _CatalogView(
                    catalog: data,
                    categoryId: _categoryId,
                    query: _query,
                    onCategory: (id) => setState(() => _categoryId = id),
                    onTap: (product) => _addAndTell(product),
                  ),
                ),
              ),
            ],
          );

          if (wide) {
            return Row(
              children: [
                Expanded(child: products),
                Container(
                  width: constraints.maxWidth >= 1300 ? 420 : 370,
                  decoration: const BoxDecoration(
                    border: Border(left: BorderSide(color: AppColors.border)),
                  ),
                  child: const CartPanel(),
                ),
              ],
            );
          }
          return Column(
            children: [
              Expanded(child: products),
              const _CartBar(),
            ],
          );
        },
      ),
    );
  }
}

class _ShiftBanner extends ConsumerWidget {
  const _ShiftBanner({required this.onOpenShift});

  final VoidCallback onOpenShift;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final shift = ref.watch(currentShiftProvider);
    final fromCache = ref.watch(catalogProvider).value?.fromCache ?? false;

    Widget banner(IconData icon, String text, {String? action, VoidCallback? onTap}) => Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
      decoration: BoxDecoration(color: AppColors.warningSoft, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppColors.warning),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: const TextStyle(color: Color(0xFF92400E))),
          ),
          if (action != null) TextButton(onPressed: onTap, child: Text(action)) else const SizedBox(height: 36),
        ],
      ),
    );

    return Column(
      children: [
        if (shift.hasValue && shift.value == null)
          banner(Icons.lock_clock, 'No open shift. Open one to count your cash drawer.', action: 'Open shift', onTap: onOpenShift),
        if (fromCache) banner(Icons.cloud_off, 'Offline: sales are saved on this device and sent when the server is back.'),
      ],
    );
  }
}

class _CatalogView extends StatelessWidget {
  const _CatalogView({required this.catalog, required this.categoryId, required this.query, required this.onCategory, required this.onTap});

  final Catalog catalog;
  final int? categoryId;
  final String query;
  final ValueChanged<int?> onCategory;
  final ValueChanged<Product> onTap;

  @override
  Widget build(BuildContext context) {
    final products = catalog.products.where((p) {
      if (categoryId != null && p.categoryId != categoryId) return false;
      if (query.isEmpty) return true;
      return p.name.toLowerCase().contains(query) || (p.barcode ?? '').contains(query) || (p.sku ?? '').toLowerCase().contains(query);
    }).toList();

    return Column(
      children: [
        SizedBox(
          height: 52,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            children: [
              _CategoryPill(label: 'All', selected: categoryId == null, onTap: () => onCategory(null)),
              for (final c in catalog.categories) _CategoryPill(label: c.name, selected: categoryId == c.id, onTap: () => onCategory(c.id)),
            ],
          ),
        ),
        const Divider(indent: 16, endIndent: 16),
        Expanded(
          child: products.isEmpty
              ? const Center(
                  child: Text('No products found', style: TextStyle(color: AppColors.muted)),
                )
              : GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                    maxCrossAxisExtent: 200,
                    mainAxisExtent: 236,
                    crossAxisSpacing: 14,
                    mainAxisSpacing: 14,
                  ),
                  itemCount: products.length,
                  itemBuilder: (context, i) => _ProductCard(product: products[i], onTap: () => onTap(products[i])),
                ),
        ),
      ],
    );
  }
}

/// Selected: filled blue pill. Others: plain text that highlights on hover.
class _CategoryPill extends StatelessWidget {
  const _CategoryPill({required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: Material(
        color: selected ? AppColors.primary : Colors.transparent,
        shape: const StadiumBorder(),
        child: InkWell(
          customBorder: const StadiumBorder(),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 15,
                color: selected ? Colors.white : AppColors.text,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({required this.product, required this.onTap});

  final Product product;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final out = product.trackStock && product.stockQty <= 0;
    final (stockText, stockColor) = !product.trackStock
        ? ('Made to order', AppColors.muted)
        : out
        ? ('Out of stock', AppColors.price)
        : product.isLowStock
        ? ('Only ${product.stockQty} left', AppColors.warning)
        : ('${product.stockQty} in stock', AppColors.success);

    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        hoverColor: AppColors.primarySoft,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ProductImage(product: product, height: 92, width: double.infinity),
              const SizedBox(height: 10),
              Expanded(
                child: Text(
                  product.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, height: 1.25),
                ),
              ),
              Text(
                usd(product.price),
                style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: AppColors.price),
              ),
              const SizedBox(height: 2),
              Row(
                children: [
                  Icon(Icons.inventory_2_outlined, size: 13, color: stockColor),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      stockText,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: stockColor, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Phone layout: a bar at the bottom that opens the cart.
class _CartBar extends ConsumerWidget {
  const _CartBar();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(cartProvider.select((c) => c.itemCount));
    final total = ref.watch(cartTotalsProvider).total;
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(54)),
            onPressed: count == 0
                ? null
                : () => showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    useSafeArea: true,
                    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
                    builder: (_) => const FractionallySizedBox(heightFactor: 0.92, child: CartPanel(inSheet: true)),
                  ),
            child: Row(
              children: [
                Badge(isLabelVisible: count > 0, label: Text('$count'), child: const Icon(Icons.shopping_bag_outlined)),
                const SizedBox(width: 12),
                Expanded(child: Text(count == 0 ? 'Tap a product to add' : 'View cart', maxLines: 1, overflow: TextOverflow.ellipsis)),
                Text('Pay · ${usd(total)}', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
