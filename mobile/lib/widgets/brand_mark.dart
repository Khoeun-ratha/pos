import 'package:flutter/material.dart';

/// The RATHA MART mark: the R drawn as a shopping cart, with its star (assets/brand, made by tool/brand_assets.py).
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 40});

  final double size;

  @override
  Widget build(BuildContext context) => Image.asset(
    'assets/brand/brand-mark.png',
    width: size,
    height: size,
    fit: BoxFit.contain,
    filterQuality: FilterQuality.medium,
    semanticLabel: 'RATHA MART',
  );
}

/// The whole logo: the mark, RATHA MART and the tagline.
class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.width = 220});

  final double width;

  @override
  Widget build(BuildContext context) => Image.asset(
    'assets/brand/logo.png',
    width: width,
    fit: BoxFit.contain,
    filterQuality: FilterQuality.medium,
    semanticLabel: 'RATHA MART',
  );
}
