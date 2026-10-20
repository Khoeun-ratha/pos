import 'package:flutter/material.dart';

/// The RATHA MART mark: a shopping bag with an R (the same drawing as the web app's favicon.svg).
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 40});

  final double size;

  @override
  Widget build(BuildContext context) =>
      SizedBox.square(dimension: size, child: CustomPaint(painter: _MarkPainter(), size: Size.square(size)));
}

class _MarkPainter extends CustomPainter {
  static const _blue = Color(0xFF1D4ED8);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.width / 64); // drawn on a 64 x 64 grid
    const box = Rect.fromLTWH(0, 0, 64, 64);
    canvas.drawRRect(
      RRect.fromRectAndRadius(box, const Radius.circular(16)),
      Paint()..shader = const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFF3B82F6), _blue]).createShader(box),
    );

    final line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    // handle
    canvas.drawPath(
      Path()
        ..moveTo(22.8, 26)
        ..cubicTo(22.8, 18.4, 26.8, 14.2, 32, 14.2)
        ..cubicTo(37.2, 14.2, 41.2, 18.4, 41.2, 26),
      line
        ..color = Colors.white
        ..strokeWidth = 3,
    );

    // bag
    canvas.drawPath(
      Path()
        ..moveTo(17.6, 24)
        ..lineTo(46.4, 24)
        ..arcToPoint(const Offset(48.4, 25.86), radius: const Radius.circular(2))
        ..lineTo(49.9, 47.46)
        ..arcToPoint(const Offset(45.5, 52), radius: const Radius.circular(4.4))
        ..lineTo(18.5, 52)
        ..arcToPoint(const Offset(14.1, 47.46), radius: const Radius.circular(4.4))
        ..lineTo(15.6, 25.86)
        ..arcToPoint(const Offset(17.6, 24), radius: const Radius.circular(2))
        ..close(),
      Paint()..color = Colors.white,
    );

    // R
    canvas.drawPath(
      Path()
        ..moveTo(27.5, 46.5)
        ..lineTo(27.5, 31.5)
        ..lineTo(33.1, 31.5)
        ..arcToPoint(const Offset(33.1, 40.5), radius: const Radius.circular(4.5))
        ..lineTo(27.5, 40.5)
        ..moveTo(32.9, 40.5)
        ..lineTo(37.9, 46.5),
      line
        ..color = _blue
        ..strokeWidth = 3.6,
    );

    canvas.drawCircle(const Offset(44, 30), 1.9, Paint()..color = const Color(0xFFF59E0B));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
