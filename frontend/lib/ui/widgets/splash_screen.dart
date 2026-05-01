import 'package:flutter/material.dart';

import '../theme.dart';
import 'app_logo_mark.dart';

/// Full-screen brand splash shown during initial bootstrap and any
/// app-level loading transition. Centers the chevron mark with a slow
/// breathing pulse and a thin progress hairline underneath.
class SplashScreen extends StatefulWidget {
  const SplashScreen({
    super.key,
    this.caption = 'AIRSIM  //  INITIALIZING',
  });

  final String caption;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedBuilder(
              animation: _ctrl,
              builder: (context, _) {
                // 0..1 triangle wave from the controller's reverse repeat.
                final t = _ctrl.value;
                final opacity = 0.55 + 0.45 * t;
                return Opacity(
                  opacity: opacity,
                  child: const AppLogoMark(size: 132, strokeWidth: 6),
                );
              },
            ),
            const SizedBox(height: 32),
            // Indeterminate hairline progress, brand-colored
            SizedBox(
              width: 132,
              height: 1.2,
              child: AnimatedBuilder(
                animation: _ctrl,
                builder: (context, _) {
                  return CustomPaint(
                    painter: _HairlineProgressPainter(progress: _ctrl.value),
                  );
                },
              ),
            ),
            const SizedBox(height: 18),
            Text(
              widget.caption,
              style: const TextStyle(
                color: AppColors.textDim,
                fontSize: 10,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HairlineProgressPainter extends CustomPainter {
  _HairlineProgressPainter({required this.progress});
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final base = Paint()
      ..color = AppColors.line2
      ..strokeWidth = size.height
      ..strokeCap = StrokeCap.square;
    canvas.drawLine(
      Offset(0, size.height / 2),
      Offset(size.width, size.height / 2),
      base,
    );

    // A short bright segment that sweeps left-to-right.
    final segW = size.width * 0.32;
    final maxX = size.width - segW;
    final x = maxX * progress;
    final fg = Paint()
      ..color = AppColors.accent
      ..strokeWidth = size.height
      ..strokeCap = StrokeCap.square;
    canvas.drawLine(
      Offset(x, size.height / 2),
      Offset(x + segW, size.height / 2),
      fg,
    );
  }

  @override
  bool shouldRepaint(covariant _HairlineProgressPainter old) =>
      old.progress != progress;
}
