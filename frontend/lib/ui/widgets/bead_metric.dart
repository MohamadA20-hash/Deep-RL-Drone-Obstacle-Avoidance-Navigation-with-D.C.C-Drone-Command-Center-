import 'package:flutter/material.dart';
import '../theme.dart';
import 'panel_card.dart';

class BeadMetricCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final String value;
  final double percent; // 0..1
  final String min;
  final String max;

  const BeadMetricCard({
    super.key,
    required this.title,
    required this.icon,
    required this.value,
    required this.percent,
    required this.min,
    required this.max,
  });

  @override
  Widget build(BuildContext context) {
    return PanelCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 12, color: AppColors.textMute),
              const SizedBox(width: 8),
              Text(title, style: AppText.cardTitle),
              const Spacer(),
              Text('${(percent * 100).toStringAsFixed(0)}%',
                  style: AppText.dataSmall.copyWith(color: AppColors.textMute)),
            ],
          ),
          const SizedBox(height: 10),
          Text(value, style: AppText.valueLarge),
          const SizedBox(height: 10),
          SizedBox(
            height: 12,
            child: CustomPaint(
              painter: _BeadBarPainter(percent: percent),
              size: const Size(double.infinity, 12),
            ),
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(min, style: AppText.label),
              Text(max, style: AppText.label),
            ],
          ),
        ],
      ),
    );
  }
}

class _BeadBarPainter extends CustomPainter {
  final double percent;
  _BeadBarPainter({required this.percent});

  @override
  void paint(Canvas canvas, Size size) {
    const beadW = 2.0;
    const gap = 4.0;
    const stride = beadW + gap;
    final cy = size.height / 2;

    final dim = Paint()
      ..color = const Color(0xFF2A323D)
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.square;
    final lit = Paint()
      ..color = AppColors.text
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.square;

    final filledX = size.width * percent;
    double x = 0;
    while (x + beadW <= size.width) {
      final p = (x + beadW <= filledX) ? lit : dim;
      canvas.drawLine(Offset(x, cy), Offset(x + beadW, cy), p);
      x += stride;
    }

    // Caret marker
    final caret = Paint()..color = AppColors.accent;
    final cx = filledX.clamp(0.0, size.width);
    final p = Path()
      ..moveTo(cx, 0)
      ..lineTo(cx - 3, -3)
      ..lineTo(cx + 3, -3)
      ..close();
    canvas.drawPath(p, caret);
    canvas.drawLine(
        Offset(cx, 0), Offset(cx, size.height), caret..strokeWidth = 1);
  }

  @override
  bool shouldRepaint(covariant _BeadBarPainter oldDelegate) =>
      oldDelegate.percent != percent;
}
