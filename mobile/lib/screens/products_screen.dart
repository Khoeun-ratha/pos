import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../models.dart';
import '../state/catalog.dart';
import '../state/session.dart';
import '../widgets/common.dart';
import '../widgets/product_image.dart';
import 'scanner_screen.dart';

final allProductsProvider = FutureProvider.autoDispose<List<Product>>((ref) async {
  // staff of a branch see (and receive / count) their branch's stock
  final branch = ref.watch(sessionProvider).user?.locationId;
  final data = await ref.watch(apiProvider).get('/api/products', query: {
    'include_inactive': 'true',
    'limit': '5000',
    if (branch != null) 'location_id': '$branch',
  });
  return [for (final p in data) Product.fromJson(p)];
});

/// Managers: edit products and receive stock.
class ProductsScreen extends ConsumerStatefulWidget {
  const ProductsScreen({super.key, this.embedded = false});

  /// Shown inside the main menu, which already has a title bar.
  final bool embedded;

  @override
  ConsumerState<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends ConsumerState<ProductsScreen> {
  String _query = '';

  void _changed() {
    ref.invalidate(allProductsProvider);
    ref.invalidate(catalogProvider);
  }

  Future<void> _edit(Product? product) async {
    final saved = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => ProductEditScreen(product: product)));
    if (saved == true) _changed();
  }

  Future<void> _stock(Product product, {required bool count}) async {
    final text = await askText(
      context,
      title: count ? 'Stock count: ${product.name}' : 'Receive stock: ${product.name}',
      label: count ? 'Quantity counted on shelf' : 'Quantity received',
      keyboard: TextInputType.number,
    );
    final qty = text == null ? null : parseWhole(text);
    if (qty == null || (!count && qty == 0)) return;
    try {
      await ref
          .read(apiProvider)
          .post(
            count ? '/api/inventory/count' : '/api/inventory/stock-in',
            count ? {'product_id': product.id, 'counted_qty': qty} : {'product_id': product.id, 'qty': qty},
          );
      _changed();
      if (mounted) showMessage(context, 'Stock updated');
    } catch (e) {
      if (mounted) showError(context, ref, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(allProductsProvider);
    return Scaffold(
      appBar: widget.embedded ? null : AppBar(title: const Text('Products')),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: null, // several screens with buttons live side by side in the menu
        onPressed: () => _edit(null),
        icon: const Icon(Icons.add),
        label: const Text('Product'),
      ),
      body: MaxWidth(
        width: 1000,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: TextField(
                decoration: const InputDecoration(
                  hintText: 'Search',
                  prefixIcon: Icon(Icons.search),
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onChanged: (v) => setState(() => _query = v.trim().toLowerCase()),
              ),
            ),
            Expanded(
              child: AsyncView<List<Product>>(
                value: products,
                onRetry: () => ref.invalidate(allProductsProvider),
                builder: (all) {
                  final list = all
                      .where((p) => _query.isEmpty || p.name.toLowerCase().contains(_query) || (p.barcode ?? '').contains(_query))
                      .toList();
                  return ListView.builder(
                    padding: const EdgeInsets.only(bottom: 80),
                    itemCount: list.length,
                    itemBuilder: (context, i) {
                      final p = list[i];
                      return ListTile(
                        leading: ProductImage(product: p, width: 44, height: 44, iconSize: 22, radius: 10),
                        title: Text(p.name, style: TextStyle(decoration: p.isActive ? null : TextDecoration.lineThrough)),
                        subtitle: Text([usd(p.price), p.categoryName ?? 'No category', if (p.barcode != null) p.barcode!].join(' • ')),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (p.trackStock)
                              Text(
                                '${p.stockQty}',
                                style: TextStyle(
                                  color: p.isLowStock ? Theme.of(context).colorScheme.error : null,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            PopupMenuButton<String>(
                              onSelected: (action) => switch (action) {
                                'in' => _stock(p, count: false),
                                'count' => _stock(p, count: true),
                                _ => _edit(p),
                              },
                              itemBuilder: (_) => [
                                const PopupMenuItem(value: 'edit', child: Text('Edit')),
                                if (p.trackStock) const PopupMenuItem(value: 'in', child: Text('Receive stock')),
                                if (p.trackStock) const PopupMenuItem(value: 'count', child: Text('Stock count')),
                              ],
                            ),
                          ],
                        ),
                        onTap: () => _edit(p),
                      );
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ProductEditScreen extends ConsumerStatefulWidget {
  const ProductEditScreen({super.key, this.product, this.barcode});

  final Product? product;

  /// Fills in a new product's barcode (one just scanned at the till).
  final String? barcode;

  @override
  ConsumerState<ProductEditScreen> createState() => _ProductEditScreenState();
}

class _ProductEditScreenState extends ConsumerState<ProductEditScreen> {
  final _form = GlobalKey<FormState>();
  late final Product? _p = widget.product;
  late final _name = TextEditingController(text: _p?.name);
  late final _barcode = TextEditingController(text: _p?.barcode ?? widget.barcode);
  late final _sku = TextEditingController(text: _p?.sku);
  late final _price = TextEditingController(text: _p == null ? '' : (_p.price / 100).toStringAsFixed(2));
  late final _cost = TextEditingController(text: _p == null ? '' : (_p.cost / 100).toStringAsFixed(2));
  late final _lowStock = TextEditingController(text: '${_p?.lowStockThreshold ?? 5}');
  final _openingStock = TextEditingController(text: '0');
  late int? _categoryId = _p?.categoryId;
  late bool _trackStock = _p?.trackStock ?? true;
  late bool _active = _p?.isActive ?? true;
  bool _busy = false;

  String? _required(String? v) => (v ?? '').trim().isEmpty ? 'Required' : null;
  String? _money(String? v) => parseDollars(v ?? '') == null ? 'Enter an amount like 1.50' : null;

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    final body = Product(
      id: _p?.id ?? 0,
      name: _name.text.trim(),
      barcode: _barcode.text.trim().isEmpty ? null : _barcode.text.trim(),
      sku: _sku.text.trim().isEmpty ? null : _sku.text.trim(),
      categoryId: _categoryId,
      price: parseDollars(_price.text)!,
      cost: parseDollars(_cost.text.isEmpty ? '0' : _cost.text) ?? 0,
      trackStock: _trackStock,
      lowStockThreshold: parseWhole(_lowStock.text) ?? 5,
      isActive: _active,
    ).toInput();
    try {
      final api = ref.read(apiProvider);
      if (_p == null) {
        await api.post('/api/products', {...body, 'stock_qty': parseWhole(_openingStock.text) ?? 0});
      } else {
        await api.put('/api/products/${_p.id}', body);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showError(context, ref, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final categories = ref.watch(catalogProvider).value?.categories ?? const <Category>[];
    return Scaffold(
      appBar: AppBar(
        title: Text(_p == null ? 'New product' : 'Edit product'),
        actions: [TextButton(onPressed: _busy ? null : _save, child: const Text('SAVE'))],
      ),
      body: Form(
        key: _form,
        child: MaxWidth(
          width: 640,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: _required,
              ),
              TextFormField(
                controller: _barcode,
                decoration: InputDecoration(
                  labelText: 'Barcode',
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.qr_code_scanner),
                    onPressed: () async {
                      final code = await ScannerScreen.scan(context);
                      if (code != null) _barcode.text = code;
                    },
                  ),
                ),
              ),
              TextFormField(
                controller: _sku,
                decoration: const InputDecoration(labelText: 'SKU (optional)'),
              ),
              DropdownButtonFormField<int?>(
                initialValue: categories.any((c) => c.id == _categoryId) ? _categoryId : null,
                decoration: const InputDecoration(labelText: 'Category'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('No category')),
                  for (final c in categories) DropdownMenuItem(value: c.id, child: Text(c.name)),
                ],
                onChanged: (v) => setState(() => _categoryId = v),
              ),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _price,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: decimalOnly,
                      decoration: const InputDecoration(labelText: 'Price (USD)', prefixText: r'$ '),
                      validator: _money,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: TextFormField(
                      controller: _cost,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: decimalOnly,
                      decoration: const InputDecoration(labelText: 'Cost (USD)', prefixText: r'$ '),
                    ),
                  ),
                ],
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Track stock'),
                value: _trackStock,
                onChanged: (v) => setState(() => _trackStock = v),
              ),
              if (_trackStock) ...[
                TextFormField(
                  controller: _lowStock,
                  keyboardType: TextInputType.number,
                  inputFormatters: digitsOnly,
                  decoration: const InputDecoration(labelText: 'Low stock warning at'),
                ),
                if (_p == null)
                  TextFormField(
                    controller: _openingStock,
                    keyboardType: TextInputType.number,
                    inputFormatters: digitsOnly,
                    decoration: const InputDecoration(labelText: 'Opening stock'),
                  ),
              ],
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('For sale (active)'),
                value: _active,
                onChanged: (v) => setState(() => _active = v),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
