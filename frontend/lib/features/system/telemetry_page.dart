import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/telemetry.dart';
import '../../core/services/telemetry_websocket_service.dart' show TrailPoint;
import '../../core/state/fleet_providers.dart';
import '../../ui/theme.dart';
import '../../ui/widgets/app_shell.dart';

class TelemetryPage extends ConsumerStatefulWidget {
  const TelemetryPage({super.key});

  @override
  ConsumerState<TelemetryPage> createState() => _TelemetryPageState();
}

class _TelemetryPageState extends ConsumerState<TelemetryPage> {
  static const int _maxSamples = 240; // ~4 min at 1Hz
  final Queue<_Sample> _samples = Queue<_Sample>();
  Timer? _ticker;
  Telemetry? _last;

  VoidCallback? _detach;
  ValueListenable<Telemetry?>? _attachedSource;

  @override
  void initState() {
    super.initState();
    // Drain the buffer on a slow tick so charts stay smooth even if telemetry
    // arrives at uneven intervals.
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      final t = _last;
      if (t == null) return;
      final live = ref.read(airsimStreamingProvider).asData?.value ?? false;
      if (!live) return;
      _samples.addLast(_Sample(
        at: DateTime.now(),
        speed: t.navrlSpeed ?? t.groundSpeed,
        altitude: t.altitude,
        battery: t.batteryLevel,
        distToGoal: t.distanceToGoal ?? double.nan,
      ));
      while (_samples.length > _maxSamples) {
        _samples.removeFirst();
      }
      if (mounted) setState(() {});
    });
  }

  void _attach(ValueListenable<Telemetry?> src) {
    if (_attachedSource == src) return;
    _detach?.call();
    void onUpdate() {
      _last = src.value;
    }

    src.addListener(onUpdate);
    _last = src.value;
    _attachedSource = src;
    _detach = () => src.removeListener(onUpdate);
  }

  @override
  void dispose() {
    _ticker?.cancel();
    _detach?.call();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final telemetryListenable = ref.watch(liveTelemetryProvider);
    final live = ref.watch(airsimStreamingProvider).asData?.value ?? false;
    final drone = ref.watch(selectedDroneProvider);
    final trail = ref.watch(liveTrailProvider);
    _attach(telemetryListenable);

    return AppShell(
      activeRoute: 'telemetry',
      title: 'Telemetry',
      subtitle:
          'Live signal // ${drone?.name.toUpperCase() ?? '— NO DRONE —'} // ${_samples.length} samples buffered',
      trailing: _LiveBadge(on: live),
      child: ValueListenableBuilder<Telemetry?>(
        valueListenable: telemetryListenable,
        builder: (context, t, _) {
          final speed =
              (live && t != null) ? (t.navrlSpeed ?? t.groundSpeed) : 0.0;
          final alt = (live && t != null) ? t.altitude : 0.0;
          final battery = (live && t != null) ? t.batteryLevel : 0.0;
          return Column(
            children: [
              SizedBox(
                height: 96,
                child: Row(
                  children: [
                    Expanded(
                        child: _StatTile(
                            label: 'SPEED',
                            value: '${speed.toStringAsFixed(2)} m/s',
                            color: AppColors.text)),
                    const SizedBox(width: 8),
                    Expanded(
                        child: _StatTile(
                            label: 'ALTITUDE',
                            value: '${alt.toStringAsFixed(2)} m',
                            color: AppColors.text)),
                    const SizedBox(width: 8),
                    Expanded(
                        child: _StatTile(
                            label: 'BATTERY',
                            value: '${battery.round()} %',
                            color: battery < 20
                                ? AppColors.alert
                                : (battery < 40
                                    ? AppColors.warn
                                    : AppColors.ok))),
                    const SizedBox(width: 8),
                    Expanded(
                        child: _StatTile(
                            label: 'GOAL DIST',
                            value: t?.distanceToGoal == null
                                ? '—'
                                : '${t!.distanceToGoal!.toStringAsFixed(2)} m',
                            color: AppColors.accent)),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      flex: 3,
                      child: Column(
                        children: [
                          Expanded(
                            child: _ChartPanel(
                              title: 'SPEED  //  m/s',
                              samples: _samples,
                              extractor: (s) => s.speed,
                              color: AppColors.accent,
                              minY: 0,
                              suggestedMaxY: 12,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Expanded(
                            child: _ChartPanel(
                              title: 'ALTITUDE  //  m AGL',
                              samples: _samples,
                              extractor: (s) => s.altitude,
                              color: AppColors.ok,
                              minY: 0,
                              suggestedMaxY: 60,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Expanded(
                            child: _ChartPanel(
                              title: 'BATTERY  //  %',
                              samples: _samples,
                              extractor: (s) => s.battery,
                              color: AppColors.warn,
                              minY: 0,
                              suggestedMaxY: 100,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      flex: 2,
                      child: Column(
                        children: [
                          Expanded(
                            flex: 3,
                            child: _PanelHeader(
                              title: 'NED TRAIL',
                              child: ValueListenableBuilder<List<TrailPoint>>(
                                valueListenable: trail,
                                builder: (_, points, __) =>
                                    CustomPaint(painter: _TrailPainter(points)),
                              ),
                            ),
                          ),
                          const SizedBox(height: 8),
                          Expanded(
                            flex: 2,
                            child: _PanelHeader(
                              title: 'RAW FRAME',
                              child: SingleChildScrollView(
                                padding: const EdgeInsets.all(10),
                                child: SelectableText(
                                  _formatRaw(t, live),
                                  style: const TextStyle(
                                    color: AppColors.textDim,
                                    fontFamily: 'Courier',
                                    fontSize: 10.5,
                                    height: 1.4,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

String _formatRaw(Telemetry? t, bool live) {
  if (!live) return '— NO LIVE STREAM —';
  if (t == null) return '— AWAITING FIRST FRAME —';
  final lines = <String>[
    'ts          : ${t.timestamp ?? '-'}',
    'droneId     : ${t.droneId ?? '-'}',
    'lat / lon   : ${t.latitude.toStringAsFixed(6)}  ${t.longitude.toStringAsFixed(6)}',
    'altitude    : ${t.altitude.toStringAsFixed(3)} m',
    'velocity    : vx=${t.velocityX.toStringAsFixed(3)}  vy=${t.velocityY.toStringAsFixed(3)}  vz=${t.velocityZ.toStringAsFixed(3)}',
    'attitude    : yaw=${t.yaw.toStringAsFixed(3)}  pitch=${t.pitch.toStringAsFixed(3)}  roll=${t.roll.toStringAsFixed(3)}',
    'battery     : ${t.batteryLevel.toStringAsFixed(1)} %',
    'obstacle    : ${t.obstacleDistance.toStringAsFixed(2)} m',
    if (t.positionNedX != null)
      'ned         : x=${t.positionNedX!.toStringAsFixed(2)}  y=${t.positionNedY!.toStringAsFixed(2)}  z=${t.positionNedZ!.toStringAsFixed(2)}',
    if (t.distanceToGoal != null)
      'distToGoal  : ${t.distanceToGoal!.toStringAsFixed(3)} m',
    if (t.navrlSpeed != null)
      'navrlSpeed  : ${t.navrlSpeed!.toStringAsFixed(3)} m/s',
    if (t.altitudeMode != null) 'altitudeMode: ${t.altitudeMode}',
    if (t.stuckReplanCount != null) 'stuckReplan : ${t.stuckReplanCount}',
  ];
  return lines.join('\n');
}

class _Sample {
  final DateTime at;
  final double speed;
  final double altitude;
  final double battery;
  final double distToGoal;
  _Sample({
    required this.at,
    required this.speed,
    required this.altitude,
    required this.battery,
    required this.distToGoal,
  });
}

class _StatTile extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _StatTile(
      {required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        border: Border.all(color: AppColors.line, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: const TextStyle(
                color: AppColors.textMute,
                fontSize: 9.5,
                letterSpacing: 1.6,
                fontWeight: FontWeight.w500,
              )),
          Text(value,
              style: TextStyle(
                color: color,
                fontSize: 22,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.4,
              )),
        ],
      ),
    );
  }
}

class _LiveBadge extends StatelessWidget {
  final bool on;
  const _LiveBadge({required this.on});
  @override
  Widget build(BuildContext context) {
    final c = on ? AppColors.ok : AppColors.alert;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.panel2,
        border: Border.all(color: c, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Text(on ? 'LIVE' : 'OFFLINE',
              style: TextStyle(
                color: c,
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.6,
              )),
        ],
      ),
    );
  }
}

class _PanelHeader extends StatelessWidget {
  final String title;
  final Widget child;
  const _PanelHeader({required this.title, required this.child});
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel,
        border: Border.all(color: AppColors.line, width: 1),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: AppColors.line, width: 1),
              ),
            ),
            alignment: Alignment.centerLeft,
            child: Text(title,
                style: const TextStyle(
                  color: AppColors.textDim,
                  fontSize: 9.5,
                  letterSpacing: 1.8,
                  fontWeight: FontWeight.w600,
                )),
          ),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _ChartPanel extends StatelessWidget {
  final String title;
  final Iterable<_Sample> samples;
  final double Function(_Sample) extractor;
  final Color color;
  final double minY;
  final double suggestedMaxY;
  const _ChartPanel({
    required this.title,
    required this.samples,
    required this.extractor,
    required this.color,
    required this.minY,
    required this.suggestedMaxY,
  });

  @override
  Widget build(BuildContext context) {
    return _PanelHeader(
      title: title,
      child: CustomPaint(
        painter: _LineChartPainter(
          values: samples.map(extractor).toList(growable: false),
          color: color,
          minY: minY,
          suggestedMaxY: suggestedMaxY,
        ),
      ),
    );
  }
}

class _LineChartPainter extends CustomPainter {
  final List<double> values;
  final Color color;
  final double minY;
  final double suggestedMaxY;
  _LineChartPainter({
    required this.values,
    required this.color,
    required this.minY,
    required this.suggestedMaxY,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTWH(8, 6, size.width - 16, size.height - 12);
    // grid
    final grid = Paint()
      ..color = AppColors.line
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.5;
    for (int i = 0; i <= 4; i++) {
      final y = rect.top + rect.height * i / 4;
      canvas.drawLine(Offset(rect.left, y), Offset(rect.right, y), grid);
    }

    if (values.isEmpty) return;

    double maxV = suggestedMaxY;
    double minV = minY;
    for (final v in values) {
      if (v.isNaN) continue;
      if (v > maxV) maxV = v;
      if (v < minV) minV = v;
    }
    if (maxV - minV < 0.001) maxV = minV + 1;

    final path = Path();
    final n = values.length;
    bool started = false;
    for (int i = 0; i < n; i++) {
      final v = values[i];
      if (v.isNaN) continue;
      final x = rect.left + (n == 1 ? 0 : rect.width * i / (n - 1));
      final y = rect.bottom - (v - minV) / (maxV - minV) * rect.height;
      if (!started) {
        path.moveTo(x, y);
        started = true;
      } else {
        path.lineTo(x, y);
      }
    }
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(path, stroke);

    // axis labels (min/max)
    final tp = TextPainter(textDirection: TextDirection.ltr);
    void drawText(String s, Offset at, {Color c = AppColors.textMute}) {
      tp.text = TextSpan(
        text: s,
        style: TextStyle(color: c, fontSize: 9, letterSpacing: 1.0),
      );
      tp.layout();
      tp.paint(canvas, at);
    }

    drawText(maxV.toStringAsFixed(maxV >= 100 ? 0 : 1),
        Offset(rect.left, rect.top - 1));
    drawText(minV.toStringAsFixed(1), Offset(rect.left, rect.bottom - 10));

    // last value pin
    if (started) {
      final lastValid =
          values.lastWhere((v) => !v.isNaN, orElse: () => double.nan);
      if (!lastValid.isNaN) {
        final lastY =
            rect.bottom - (lastValid - minV) / (maxV - minV) * rect.height;
        canvas.drawCircle(
            Offset(rect.right, lastY), 2.4, Paint()..color = color);
        drawText(
          lastValid.toStringAsFixed(2),
          Offset(rect.right - 50, lastY - 14),
          c: color,
        );
      }
    }
  }

  @override
  bool shouldRepaint(covariant _LineChartPainter old) => true;
}

class _TrailPainter extends CustomPainter {
  final List<TrailPoint> points;
  _TrailPainter(this.points);

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTWH(8, 8, size.width - 16, size.height - 16);
    // backdrop grid
    final grid = Paint()
      ..color = AppColors.line
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.5;
    for (int i = 0; i <= 6; i++) {
      final x = rect.left + rect.width * i / 6;
      canvas.drawLine(Offset(x, rect.top), Offset(x, rect.bottom), grid);
      final y = rect.top + rect.height * i / 6;
      canvas.drawLine(Offset(rect.left, y), Offset(rect.right, y), grid);
    }

    if (points.isEmpty) {
      final tp = TextPainter(
        text: const TextSpan(
          text: '— NO TRAIL —',
          style: TextStyle(
              color: AppColors.textMute, fontSize: 10, letterSpacing: 2),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(
        canvas,
        Offset(rect.center.dx - tp.width / 2, rect.center.dy - tp.height / 2),
      );
      return;
    }

    double minX = double.infinity, maxX = -double.infinity;
    double minY = double.infinity, maxY = -double.infinity;
    for (final p in points) {
      final x = p.east;
      final y = p.north;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    // pad
    final spanX = (maxX - minX).abs() < 1 ? 1 : (maxX - minX);
    final spanY = (maxY - minY).abs() < 1 ? 1 : (maxY - minY);
    final span = spanX > spanY ? spanX : spanY;
    final cx = (minX + maxX) / 2;
    final cy = (minY + maxY) / 2;
    final scale = (rect.width.clamp(0, rect.height)) / (span * 1.2);

    Offset project(double x, double y) {
      final px = rect.center.dx + (x - cx) * scale;
      final py = rect.center.dy - (y - cy) * scale; // flip Y for screen
      return Offset(px, py);
    }

    final path = Path();
    for (int i = 0; i < points.length; i++) {
      final o = project(points[i].east, points[i].north);
      if (i == 0) {
        path.moveTo(o.dx, o.dy);
      } else {
        path.lineTo(o.dx, o.dy);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = AppColors.accent
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4,
    );
    final last = points.last;
    canvas.drawCircle(
        project(last.east, last.north), 3.2, Paint()..color = AppColors.accent);
  }

  @override
  bool shouldRepaint(covariant _TrailPainter old) => true;
}
