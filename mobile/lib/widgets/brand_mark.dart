import 'package:flutter/material.dart';

/// The RATHA MART mark: an R drawn as a shopping cart (the same drawing as the web app's favicon.svg).
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 40});

  final double size;

  @override
  Widget build(BuildContext context) =>
      SizedBox.square(dimension: size, child: CustomPaint(painter: _MarkPainter(), size: Size.square(size)));
}

class _MarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.width / 64); // drawn on a 64 x 64 grid
    const box = Rect.fromLTWH(0, 0, 64, 64);
    canvas.drawRRect(
      RRect.fromRectAndRadius(box, const Radius.circular(16)),
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF3B82F6), Color(0xFF1E40AF)],
        ).createShader(box),
    );

    // handle and stem, basket (the R's bowl), its slanted front (the R's leg)
    canvas.drawPath(
      Path()
        ..moveTo(17, 14)
        ..lineTo(25, 14)
        ..lineTo(25, 41)
        ..lineTo(47, 41)
        ..moveTo(25, 14)
        ..lineTo(37.5, 14)
        ..arcToPoint(const Offset(37.5, 31), radius: const Radius.circular(8.5))
        ..lineTo(25, 31)
        ..moveTo(35, 31)
        ..lineTo(46, 41),
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 5.4
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );

    final wheel = Paint()..color = const Color(0xFFFBBF24);
    canvas.drawCircle(const Offset(28, 49.5), 3.7, wheel);
    canvas.drawCircle(const Offset(44, 49.5), 3.7, wheel);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
