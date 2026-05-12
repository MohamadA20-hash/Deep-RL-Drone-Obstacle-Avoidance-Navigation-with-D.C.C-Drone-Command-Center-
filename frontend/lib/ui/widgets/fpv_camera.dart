import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';
import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';
import '../theme.dart';
import 'panel_card.dart';

/// FPV camera panel.
///
/// The Python AirSim auto-bridge runs an HTTP server on
/// `http://localhost:8766/fpv` that serves a fresh PNG (Scene camera "0" on
/// "Drone1") on every GET. We poll it ourselves with a [Dio] client and feed
/// the bytes into [Image.memory] so the rendering path is independent of
/// Flutter's Image.network state machine — that gives us deterministic
/// recovery after the bridge restarts and lets us decide "no signal" purely
/// from the wall-clock of the last successful frame.
class FpvCamera extends ConsumerStatefulWidget {
  const FpvCamera({super.key, this.expanded = false, this.onClose});

  /// `true` when displayed in the fullscreen dialog. Hides the title bar
  /// chrome and shows a close button instead.
  final bool expanded;
  final VoidCallback? onClose;

  @override
  ConsumerState<FpvCamera> createState() => _FpvCameraState();
}

class _FpvCameraState extends ConsumerState<FpvCamera> {
  // Override at build time with --dart-define=FPV_BASE_URL=http://<host>:8766/fpv
  // (e.g. for an Android phone pointing at the laptop's LAN IP).
  static const String _fpvBaseUrl = String.fromEnvironment(
    'FPV_BASE_URL',
    defaultValue: 'http://localhost:8766/fpv',
  );
  static const Duration _refreshInterval = Duration(milliseconds: 100);
  static const Duration _staleWindow = Duration(seconds: 2);

  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 2),
    receiveTimeout: const Duration(seconds: 2),
    responseType: ResponseType.bytes,
  ));
  Timer? _ticker;
  Uint8List? _lastFrame;
  DateTime? _lastFrameAt;
  bool _inFlight = false;

  @override
  void initState() {
    super.initState();
    _ticker = Timer.periodic(_refreshInterval, (_) => _fetch());
    // Kick off immediately so the first frame doesn't wait 100 ms.
    _fetch();
  }

  Future<void> _fetch() async {
    if (!mounted || _inFlight) return;
    _inFlight = true;
    try {
      // No cache-buster query string: the bridge handler compares
      // `self.path != '/fpv'` strictly, so any `?t=…` suffix returns 404.
      // The bridge already sends `Cache-Control: no-cache, no-store`, so
      // the buster is unnecessary anyway.
      final r = await _dio.get<List<int>>(
        _fpvBaseUrl,
        options: Options(
          responseType: ResponseType.bytes,
          // Treat 204 (no frame yet) as a soft miss, not an error.
          validateStatus: (s) => s != null && s < 500,
        ),
      );
      final bytes = r.data;
      if (r.statusCode == 200 && bytes != null && bytes.length > 100) {
        if (!mounted) return;
        setState(() {
          _lastFrame = Uint8List.fromList(bytes);
          _lastFrameAt = DateTime.now();
        });
      } else {
        // 204 (bridge cleared the frame) or empty body — drop the stale
        // image so the OFFLINE overlay can take over instead of a freeze.
        if (_lastFrame != null && mounted) {
          final stale = _lastFrameAt == null ||
              DateTime.now().difference(_lastFrameAt!) > _staleWindow;
          if (stale) {
            setState(() => _lastFrame = null);
          }
        }
      }
    } catch (_) {
      // Connection refused / timeout — bridge or AirSim down. Just retry next tick.
    } finally {
      _inFlight = false;
    }
  }

  @override
  void dispose() {
    _ticker?.cancel();
    _dio.close(force: true);
    super.dispose();
  }

  void _openFullscreen() {
    showDialog(
      context: context,
      barrierColor: Colors.black,
      useRootNavigator: true,
      builder: (ctx) => Dialog(
        insetPadding: EdgeInsets.zero,
        backgroundColor: Colors.black,
        child: SizedBox.expand(
          child: FpvCamera(
            expanded: true,
            onClose: () => Navigator.of(ctx).pop(),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // FPV is sourced from the bridge's standalone HTTP server (port 8766).
    // It is INDEPENDENT of the telemetry websocket — if the camera is
    // serving frames we treat the feed as live, regardless of whether the
    // telemetry stream provider says AirSim is streaming. (Operators were
    // seeing "NO SIGNAL" while the camera was clearly broadcasting because
    // the telemetry websocket was momentarily reconnecting.)
    final hasRecentFrame = _lastFrameAt != null &&
        DateTime.now().difference(_lastFrameAt!) <= _staleWindow;
    final showOffline = !hasRecentFrame;

    Widget content = ClipRect(
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Last good FPV frame (kept on screen even between fetches so the
          // stream looks gapless at 10–15 fps).
          if (_lastFrame != null)
            Positioned.fill(
              child: Image.memory(
                _lastFrame!,
                fit: BoxFit.cover,
                gaplessPlayback: true,
                filterQuality: FilterQuality.low,
              ),
            ),
          // HUD overlay drawn on top of the live frame.
          CustomPaint(painter: _HudOverlayPainter()),
          // No-signal blackout when AirSim isn't streaming a feed.
          if (showOffline) const _FpvOfflineOverlay(),
          // Top-left meta
          const Positioned(
            top: 8,
            left: 8,
            child: Text(
              'CAM-1 // 1920\u00d71080 // 30 FPS',
              style: TextStyle(
                color: AppColors.text,
                fontSize: 9,
                letterSpacing: 1.4,
                fontWeight: FontWeight.w500,
                fontFamilyFallback: ['Consolas', 'monospace'],
              ),
            ),
          ),
          // Top-right REC indicator + fullscreen / close button
          Positioned(
            top: 6,
            right: 6,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const StatusDot(color: AppColors.alert, size: 5),
                const SizedBox(width: 5),
                const Text('REC',
                    style: TextStyle(
                      color: AppColors.alert,
                      fontSize: 9,
                      letterSpacing: 1.6,
                      fontWeight: FontWeight.w600,
                    )),
                const SizedBox(width: 10),
                _FpvIconBtn(
                  icon: widget.expanded ? Icons.close : Icons.fullscreen,
                  tooltip: widget.expanded ? 'Close' : 'Fullscreen',
                  onTap: widget.expanded ? widget.onClose : _openFullscreen,
                ),
              ],
            ),
          ),
          // Bottom-left telemetry
          Positioned(
            bottom: 8,
            left: 8,
            child: Row(
              children: const [
                _HudPair(k: 'GIMBAL', v: '\u221202.0\u00b0'),
                SizedBox(width: 12),
                _HudPair(k: 'ZOOM', v: '1.0\u00d7'),
                SizedBox(width: 12),
                _HudPair(k: 'ISO', v: '400'),
              ],
            ),
          ),
          // Bottom-right
          const Positioned(
            bottom: 8,
            right: 8,
            child: _HudPair(k: 'TGT', v: 'NONE'),
          ),
        ],
      ),
    );

    if (widget.expanded) {
      return Material(color: Colors.black, child: content);
    }
    return PanelCard(
      padding: const EdgeInsets.all(10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('FPV', style: AppText.cardTitle),
              const SizedBox(width: 10),
              const Text('CAM-1 // RGB', style: AppText.cardSub),
              const Spacer(),
              InlineStatus(
                text: showOffline ? 'OFFLINE' : 'STREAM',
                color: showOffline ? AppColors.alert : AppColors.ok,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Expanded(child: content),
        ],
      ),
    );
  }
}

class _FpvIconBtn extends StatelessWidget {
  final IconData icon;
  final String? tooltip;
  final VoidCallback? onTap;
  const _FpvIconBtn({required this.icon, this.tooltip, this.onTap});
  @override
  Widget build(BuildContext context) {
    final btn = GestureDetector(
      onTap: onTap,
      child: Container(
        width: 22,
        height: 22,
        decoration: BoxDecoration(
          color: Colors.black.withOpacity(0.55),
          border: Border.all(color: AppColors.line2),
        ),
        child: Icon(icon, size: 13, color: AppColors.text),
      ),
    );
    return tooltip == null ? btn : Tooltip(message: tooltip!, child: btn);
  }
}

class _FpvOfflineOverlay extends StatelessWidget {
  const _FpvOfflineOverlay();
  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // Solid blackout so the synthetic scene doesn't bleed through.
        Container(color: Colors.black.withOpacity(0.86)),
        // SMPTE-style "NO SIGNAL" centered.
        Center(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.alert.withOpacity(0.18),
              border: Border.all(color: AppColors.alert, width: 1.0),
              borderRadius: BorderRadius.circular(2),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: const [
                StatusDot(color: AppColors.alert, size: 7),
                SizedBox(width: 10),
                Text(
                  'FPV  //  NO SIGNAL',
                  style: TextStyle(
                    color: AppColors.alert,
                    fontSize: 13,
                    letterSpacing: 2.4,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ),
        // Subtitle below the pill.
        const Positioned(
          left: 0,
          right: 0,
          bottom: 32,
          child: Center(
            child: Text(
              'AIRSIM OFFLINE  //  WAITING FOR CAMERA BROADCAST…',
              style: TextStyle(
                color: AppColors.textDim,
                fontSize: 9.5,
                letterSpacing: 1.6,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _HudPair extends StatelessWidget {
  final String k;
  final String v;
  const _HudPair({required this.k, required this.v});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(k,
            style: const TextStyle(
              color: AppColors.textMute,
              fontSize: 9,
              letterSpacing: 1.4,
              fontWeight: FontWeight.w500,
            )),
        const SizedBox(width: 5),
        Text(v,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 9.5,
              letterSpacing: 0.8,
              fontWeight: FontWeight.w600,
              fontFamilyFallback: ['Consolas', 'monospace'],
            )),
      ],
    );
  }
}

class _FpvScenePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // Sky — flat dark with subtle gradient
    final sky = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF1A2230), Color(0xFF12181F)],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height * 0.55));
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height * 0.55), sky);

    // Ground
    final ground = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [Color(0xFF0E141B), Color(0xFF06090D)],
      ).createShader(
          Rect.fromLTWH(0, size.height * 0.55, size.width, size.height * 0.45));
    canvas.drawRect(
        Rect.fromLTWH(0, size.height * 0.55, size.width, size.height * 0.45),
        ground);

    // Building silhouettes
    final building = Paint()..color = const Color(0xFF1B2230);
    final winPaint = Paint()..color = const Color(0xFF2A3548);
    final r = size.width * 0.07;
    double x = 0;
    int idx = 0;
    while (x < size.width) {
      final h = (size.height * 0.30) + ((idx * 17) % 60) - 25;
      final top = size.height * 0.55 - h;
      canvas.drawRect(Rect.fromLTWH(x, top, r, h), building);
      // window dots
      for (double yy = top + 5; yy < top + h - 4; yy += 7) {
        for (double xx = x + 4; xx < x + r - 4; xx += 5) {
          if ((xx.toInt() + yy.toInt()) % 11 < 7) {
            canvas.drawRect(Rect.fromLTWH(xx, yy, 1.5, 1.5), winPaint);
          }
        }
      }
      x += r + 1;
      idx++;
    }

    // Road grid lines on ground (perspective)
    final road = Paint()
      ..color = const Color(0xFF1F2632)
      ..strokeWidth = 0.7;
    for (int i = 0; i < 6; i++) {
      final y = size.height * 0.55 + (i * i) * size.height * 0.012;
      if (y < size.height) {
        canvas.drawLine(Offset(0, y), Offset(size.width, y), road);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _FpvScenePainter oldDelegate) => false;
}

// Chart-style HUD: corner brackets, ladder, heading tape, reticle.
class _HudOverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final lineColor = AppColors.text.withOpacity(0.55);
    final faint = AppColors.text.withOpacity(0.22);
    final accent = AppColors.accent.withOpacity(0.85);

    final stroke = Paint()
      ..color = lineColor
      ..strokeWidth = 1.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.square;

    const arm = 14.0;
    const pad = 4.0;
    // Corner brackets
    final corners = [
      Offset(pad, pad),
      Offset(size.width - pad, pad),
      Offset(pad, size.height - pad),
      Offset(size.width - pad, size.height - pad),
    ];
    final dirs = [
      [const Offset(arm, 0), const Offset(0, arm)],
      [const Offset(-arm, 0), const Offset(0, arm)],
      [const Offset(arm, 0), const Offset(0, -arm)],
      [const Offset(-arm, 0), const Offset(0, -arm)],
    ];
    for (int i = 0; i < 4; i++) {
      canvas.drawLine(corners[i], corners[i] + dirs[i][0], stroke);
      canvas.drawLine(corners[i], corners[i] + dirs[i][1], stroke);
    }

    final cx = size.width / 2;
    final cy = size.height / 2;

    // Horizon (dotted)
    final dotPaint = Paint()..color = faint;
    for (double x = 8; x < size.width - 8; x += 4) {
      canvas.drawRect(Rect.fromLTWH(x, cy, 2, 0.7), dotPaint);
    }

    // Pitch ladder (left + right of center, every 10°)
    final ladder = Paint()
      ..color = lineColor
      ..strokeWidth = 1;
    for (int p = -20; p <= 20; p += 10) {
      if (p == 0) continue;
      final y = cy - p * 1.2;
      const lw = 22.0;
      canvas.drawLine(Offset(cx - 60, y), Offset(cx - 60 + lw, y), ladder);
      canvas.drawLine(Offset(cx + 60 - lw, y), Offset(cx + 60, y), ladder);
      // tick label
      final tp = TextPainter(
        text: TextSpan(
          text: p.abs().toString(),
          style: const TextStyle(
            color: AppColors.text,
            fontSize: 8,
            fontWeight: FontWeight.w500,
            fontFamilyFallback: ['Consolas', 'monospace'],
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(cx - 60 - tp.width - 3, y - tp.height / 2));
      tp.paint(canvas, Offset(cx + 60 + 3, y - tp.height / 2));
    }

    // Center reticle: target square + cross
    final reticle = Paint()
      ..color = accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;
    canvas.drawRect(
        Rect.fromCenter(center: Offset(cx, cy), width: 22, height: 22),
        reticle);
    // Side ticks
    canvas.drawLine(Offset(cx - 16, cy), Offset(cx - 11, cy), reticle);
    canvas.drawLine(Offset(cx + 11, cy), Offset(cx + 16, cy), reticle);
    canvas.drawLine(Offset(cx, cy - 16), Offset(cx, cy - 11), reticle);
    canvas.drawLine(Offset(cx, cy + 11), Offset(cx, cy + 16), reticle);
    // Center dot
    canvas.drawCircle(Offset(cx, cy), 1.2, Paint()..color = accent);

    // Heading tape (top)
    final tapePaint = Paint()
      ..color = faint
      ..strokeWidth = 0.8;
    const tapeY = 20.0;
    canvas.drawLine(Offset(cx - 70, tapeY), Offset(cx + 70, tapeY), tapePaint);
    final headings = [310, 320, 330, 340, 350, 0, 10, 20];
    for (int i = 0; i < headings.length; i++) {
      final x = cx - 70 + (i * 20.0);
      canvas.drawLine(Offset(x, tapeY), Offset(x, tapeY - 3), tapePaint);
    }
    // Active heading marker
    final hdgMark = Paint()..color = accent;
    final triPath = Path()
      ..moveTo(cx, tapeY + 4)
      ..lineTo(cx - 4, tapeY + 10)
      ..lineTo(cx + 4, tapeY + 10)
      ..close();
    canvas.drawPath(triPath, hdgMark);
    final hdgText = TextPainter(
      text: const TextSpan(
        text: '034',
        style: TextStyle(
          color: AppColors.text,
          fontSize: 10,
          fontWeight: FontWeight.w600,
          fontFamilyFallback: ['Consolas', 'monospace'],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    hdgText.paint(canvas, Offset(cx - hdgText.width / 2, tapeY + 12));

    // Roll arc (bottom)
    final arcRect =
        Rect.fromCenter(center: Offset(cx, cy + 60), width: 130, height: 130);
    canvas.drawArc(
        arcRect,
        math.pi * 1.2,
        math.pi * 0.6,
        false,
        Paint()
          ..color = faint
          ..strokeWidth = 0.8
          ..style = PaintingStyle.stroke);
    // Roll indicator triangle at top of arc
    final rollMark = Paint()..color = lineColor;
    final rollPath = Path()
      ..moveTo(cx, cy + 60 - 65)
      ..lineTo(cx - 3.5, cy + 60 - 60)
      ..lineTo(cx + 3.5, cy + 60 - 60)
      ..close();
    canvas.drawPath(rollPath, rollMark);
  }

  @override
  bool shouldRepaint(covariant _HudOverlayPainter oldDelegate) => false;
}
