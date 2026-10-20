import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../models.dart';
import 'scan.dart';
import 'session.dart';

class Catalog {
  const Catalog({required this.categories, required this.products, this.fromCache = false});

  final List<Category> categories;
  final List<Product> products;

  /// True when the server was unreachable and the last saved copy is shown.
  final bool fromCache;

  /// The product with this barcode or SKU (UPC-A / EAN-13 forms and Khmer digits match too; SKUs ignore case).
  Product? byCode(String code) {
    final variants = codeVariants(code);
    final lower = cleanCode(code).toLowerCase();
    for (final p in products) {
      if (variants.contains(p.barcode) || p.sku?.toLowerCase() == lower) return p;
    }
    return null;
  }
}

/// Products and categories, cached on the phone so selling works offline.
class CatalogNotifier extends AsyncNotifier<Catalog> {
  static const _cacheKey = 'catalog_cache';

  @override
  Future<Catalog> build() async {
    final api = ref.watch(apiProvider);
    final prefs = ref.read(prefsProvider);
    try {
      final results = await Future.wait([api.get('/api/categories'), api.get('/api/products')]);
      await prefs.setString(_cacheKey, jsonEncode({'categories': results[0], 'products': results[1]}));
      return _parse(results[0], results[1]);
    } on ApiException catch (e) {
      final cached = prefs.getString(_cacheKey);
      if (!e.isNetwork || cached == null) rethrow;
      final data = jsonDecode(cached);
      return _parse(data['categories'], data['products'], fromCache: true);
    }
  }

  Catalog _parse(List<dynamic> categories, List<dynamic> products, {bool fromCache = false}) => Catalog(
    categories: [for (final c in categories) Category.fromJson(c)],
    products: [for (final p in products) Product.fromJson(p)],
    fromCache: fromCache,
  );

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }
}

final catalogProvider = AsyncNotifierProvider<CatalogNotifier, Catalog>(CatalogNotifier.new);
