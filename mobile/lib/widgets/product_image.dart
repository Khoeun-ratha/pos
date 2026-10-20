import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme.dart';
import '../models.dart';
import '../state/session.dart';

/// The product's photo from the server, or its coloured category icon when it has none
/// (or the photo cannot be loaded, e.g. offline).
class ProductImage extends ConsumerWidget {
  const ProductImage({super.key, required this.product, this.width, this.height, this.iconSize = 40, this.radius = 12});

  final Product product;
  final double? width, height;
  final double iconSize, radius;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final art = categoryArt(product.categoryName);
    final icon = Container(
      width: width,
      height: height,
      color: art.background,
      child: Icon(art.icon, size: iconSize, color: art.foreground),
    );
    final path = product.imageUrl;
    final serverUrl = ref.watch(sessionProvider.select((s) => s.serverUrl));
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: path == null
          ? icon
          : Image.network(
              '$serverUrl$path',
              width: width,
              height: height,
              fit: BoxFit.cover,
              semanticLabel: product.name,
              errorBuilder: (_, _, _) => icon,
              loadingBuilder: (context, child, progress) =>
                  progress == null ? child : Container(width: width, height: height, color: AppColors.page),
            ),
    );
  }
}
