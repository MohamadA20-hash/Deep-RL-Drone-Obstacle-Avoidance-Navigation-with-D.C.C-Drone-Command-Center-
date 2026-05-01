import 'package:flutter/material.dart';

import '../theme.dart';

/// App mark used in the splash / loading screen.
///
/// A tall, thin isoceles chevron outlined in cool slate with a small warm
/// amber bar centered beneath it. Matches the brand reference exactly.
class AppLogoMark extends StatelessWidget {
  const AppLogoMark({
    super.key,
    this.size = 120,
    this.lineColor = AppColors.text,
    this.barColor = AppColors.accent,
    this.strokeWidth = 6,
  });

  final double size;
  final Color lineColor;
  final Color barColor;
  final double strokeWidth;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      // Logo is a touch taller than wide (true peak proportions).
      height: size * 1.05,
      child: CustomPaint(
        painter: _LogoPainter(
          lineColor: lineColor,
          barColor: barColor,
          strokeWidth: strokeWidth,
        ),
      ),
    );
  }
}

class _LogoPainter extends CustomPainter {
  _LogoPainter({
    required this.lineColor,
    required this.barColor,
    required this.strokeWidth,
  });

  final Color lineColor;
  final Color barColor;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    // Reference layout (normalised to canvas):
    //   apex at (0.5, 0.07)
    //   base feet at (0.18, 0.86) and (0.82, 0.86)
    //   amber bar centered at (0.5, 0.93), width 0.20, height 0.025
    final apex = Offset(w * 0.5, h * 0.07);
    final left = Offset(w * 0.18, h * 0.86);
    final right = Offset(w * 0.82, h * 0.86);

    final stroke = Paint()
      ..color = lineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeJoin = StrokeJoin.miter
      ..strokeCap = StrokeCap.butt
      ..isAntiAlias = true;

    final path = Path()
      ..moveTo(left.dx, left.dy)
      ..lineTo(apex.dx, apex.dy)
      ..lineTo(right.dx, right.dy);
    canvas.drawPath(path, stroke);

    // Amber bar
    final barW = w * 0.20;
    final barH = h * 0.025;
    final barRect = Rect.fromCenter(
      center: Offset(w * 0.5, h * 0.945),
      width: barW,
      height: barH,
    );
    final barPaint = Paint()..color = barColor;
    canvas.drawRect(barRect, barPaint);
  }

  @override
  bool shouldRepaint(covariant _LogoPainter old) {
    return old.lineColor != lineColor ||
        old.barColor != barColor ||
        old.strokeWidth != strokeWidth;
  }
}
