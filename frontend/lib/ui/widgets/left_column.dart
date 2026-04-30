import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:math' as math;
import '../../core/models/command.dart';
import '../../core/models/telemetry.dart';
import '../../core/state/fleet_providers.dart';
import '../theme.dart';
import 'command_dispatcher.dart';
import 'panel_card.dart';

class LeftColumn extends ConsumerWidget {
  const LeftColumn({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dispatcher = CommandDispatcher(ref, context);
    final telemetryListenable = ref.watch(liveTelemetryProvider);
    final drone = ref.watch(selectedDroneProvider);
    final live = ref.watch(airsimStreamingProvider).asData?.value ?? false;

    return SingleChildScrollView(
      child: ValueListenableBuilder<Telemetry?>(
        valueListenable: telemetryListenable,
        builder: (context, tRaw, _) {
          // Strip telemetry entirely when AirSim isn't streaming so the UI
          // can't accidentally surface stale numbers.
          final t = live ? tRaw : null;
          final batteryAlive = (t?.batteryLevel ?? 0) > 0;
          final closestObs = t?.closestObstacleDistance;
          final stuck = t?.stuckReplanCount ?? 0;
          final proactive = t?.proactiveReplanCount ?? 0;
          final mode = live ? (drone?.navigationMode ?? '—') : 'OFFLINE';
          final phase = live ? (drone?.flightStatus ?? 'IDLE') : 'OFFLINE';
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // MISSION
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _CardHeader(
                        title: 'MISSION', sub: 'NED // LIVE', badge: phase),
                    const SizedBox(height: 14),
                    _Row(k: 'PHASE', v: phase),
                    _Row(
                        k: 'REPLANS',
                        v: '${(t?.proactiveReplanCount ?? 0) + (t?.stuckReplanCount ?? 0)}'),
                    _Row(
                        k: 'GOAL',
                        v: t?.distanceToGoal == null
                            ? '—'
                            : '${t!.distanceToGoal!.toStringAsFixed(2)} m'),
                    const SizedBox(height: 12),
                    GhostButton(
                      label: 'SET WAYPOINT',
                      wide: true,
                      icon: Icons.add_location_alt_outlined,
                      onPressed: () =>
                          _showSetWaypointSheet(context, dispatcher),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              // CONTROL
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _CardHeader(
                        title: 'CONTROL',
                        sub: 'AUTHORITY // AIRSIM',
                        badge: mode),
                    const SizedBox(height: 12),
                    _AuthSeg(activeMode: mode),
                    const SizedBox(height: 10),
                    GhostButton(
                      label: 'TAKE CONTROL',
                      wide: true,
                      icon: Icons.front_hand_outlined,
                      onPressed: () => dispatcher.send(
                        DroneCommandType.setMode,
                        parameters: '{"mode":"MANUAL"}',
                        successLabel: 'TAKE CONTROL',
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              // SUBSYSTEMS — motor heath is currently inferred from the global
              // battery level; per-rotor health isn't published by the bridge.
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const _CardHeader(title: 'SUBSYSTEMS'),
                    const SizedBox(height: 12),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        CustomPaint(
                          size: const Size(72, 72),
                          painter: _QuadPainter(),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _MotorBlock(
                              batteryAlive: batteryAlive,
                              batteryPct: (t?.batteryLevel ?? 0) / 100.0),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Container(height: 1, color: AppColors.line),
                    const SizedBox(height: 10),
                    _Row(k: 'STUCK REPLANS', v: '$stuck'),
                    _Row(k: 'PROACTIVE', v: '$proactive'),
                    _Row(
                        k: 'OBS DIST',
                        v: closestObs == null
                            ? '—'
                            : '${closestObs.toStringAsFixed(1)} m'),
                    _Row(
                        k: 'BAT',
                        v: t == null ? '0%' : '${t.batteryLevel.round()}%'),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              // LIDAR
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const _CardHeader(title: 'LIDAR', sub: 'SCANNING'),
                    const SizedBox(height: 8),
                    AspectRatio(
                      aspectRatio: 1.05,
                      child: CustomPaint(painter: _LidarPainter()),
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

void _showSetWaypointSheet(BuildContext context, CommandDispatcher dispatcher) {
  final ctrlX = TextEditingController();
  final ctrlY = TextEditingController();
  final ctrlZ = TextEditingController(text: '-5');
  showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      backgroundColor: AppColors.panel,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: AppColors.line, width: 1),
        borderRadius: BorderRadius.circular(2),
      ),
      title: const Text('SET WAYPOINT (NED)',
          style: TextStyle(
            color: AppColors.text,
            fontSize: 12,
            letterSpacing: 2.4,
            fontWeight: FontWeight.w600,
          )),
      content: SizedBox(
        width: 280,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _coordField(ctrlX, 'X (north, m)'),
            const SizedBox(height: 8),
            _coordField(ctrlY, 'Y (east, m)'),
            const SizedBox(height: 8),
            _coordField(ctrlZ, 'Z (down, m, negative = up)'),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('CANCEL',
              style: TextStyle(
                  color: AppColors.textMute, fontSize: 10, letterSpacing: 1.6)),
        ),
        TextButton(
          onPressed: () {
            final x = double.tryParse(ctrlX.text.trim());
            final y = double.tryParse(ctrlY.text.trim());
            final z = double.tryParse(ctrlZ.text.trim());
            if (x == null || y == null || z == null) return;
            Navigator.of(ctx).pop();
            dispatcher.send(
              DroneCommandType.setGoal,
              parameters: '{"x":$x,"y":$y,"z":$z}',
              successLabel: 'WAYPOINT SET',
            );
          },
          child: const Text('SEND',
              style: TextStyle(
                  color: AppColors.accent,
                  fontSize: 10,
                  letterSpacing: 1.6,
                  fontWeight: FontWeight.w600)),
        ),
      ],
    ),
  );
}

Widget _coordField(TextEditingController c, String label) {
  return TextField(
    controller: c,
    keyboardType:
        const TextInputType.numberWithOptions(signed: true, decimal: true),
    style: const TextStyle(color: AppColors.text, fontSize: 12),
    decoration: InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: AppColors.textMute, fontSize: 10),
      border: const OutlineInputBorder(),
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
    ),
  );
}

// ---------- Building blocks ----------

class _CardHeader extends StatelessWidget {
  final String title;
  final String? sub;
  final String? badge;
  const _CardHeader({required this.title, this.sub, this.badge});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: AppText.cardTitle),
              if (sub != null) ...[
                const SizedBox(height: 3),
                Text(sub!, style: AppText.cardSub),
              ],
            ],
          ),
        ),
        if (badge != null) StatusBadge(text: badge!, color: AppColors.accent),
      ],
    );
  }
}

class _Row extends StatelessWidget {
  final String k;
  final String v;
  const _Row({required this.k, required this.v});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k,
              style: const TextStyle(
                fontSize: 9.5,
                letterSpacing: 1.4,
                color: AppColors.textMute,
                fontWeight: FontWeight.w500,
              )),
          Text(v, style: AppText.dataSmall),
        ],
      ),
    );
  }
}

class _AuthSeg extends StatelessWidget {
  final String activeMode;
  const _AuthSeg({required this.activeMode});
  @override
  Widget build(BuildContext context) {
    final m = activeMode.toUpperCase();
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel2,
        border: Border.all(color: AppColors.line2),
      ),
      child: Row(
        children: [
          _SegItem(label: 'MANUAL', active: m == 'MANUAL'),
          _SegItem(label: 'ASSIST', active: m == 'ASSIST' || m == 'ASSISTED'),
          _SegItem(
              label: 'AUTO',
              active: m == 'AUTO' ||
                  m == 'AUTONOMOUS' ||
                  m == 'AUTONAV' ||
                  m == 'NAVRL'),
        ],
      ),
    );
  }
}

class _SegItem extends StatelessWidget {
  final String label;
  final bool active;
  const _SegItem({required this.label, required this.active});
  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 6),
        decoration: BoxDecoration(
          color: active ? AppColors.panel3 : Colors.transparent,
          border: active
              ? const Border(
                  bottom: BorderSide(color: AppColors.accent, width: 1.5),
                )
              : null,
        ),
        alignment: Alignment.center,
        child: Text(
          label,
          style: TextStyle(
            fontSize: 9,
            letterSpacing: 1.4,
            fontWeight: FontWeight.w600,
            color: active ? AppColors.text : AppColors.textMute,
          ),
        ),
      ),
    );
  }
}

class _MotorBlock extends StatelessWidget {
  final bool batteryAlive;
  final double batteryPct; // 0..1
  const _MotorBlock({required this.batteryAlive, required this.batteryPct});

  @override
  Widget build(BuildContext context) {
    // Without per-motor telemetry, mirror the battery level uniformly across
    // the four rotors so the readout still reflects fleet state.
    final h = batteryAlive ? batteryPct.clamp(0.0, 1.0) : 0.0;
    return Column(
      children: [
        _MotorRow(label: 'M1', health: h),
        _MotorRow(label: 'M2', health: h),
        _MotorRow(label: 'M3', health: h),
        _MotorRow(label: 'M4', health: h),
      ],
    );
  }
}

class _MotorRow extends StatelessWidget {
  final String label;
  final double health; // 0..1
  const _MotorRow({required this.label, required this.health});

  @override
  Widget build(BuildContext context) {
    final Color barColor = health >= 0.90
        ? AppColors.text
        : health >= 0.75
            ? AppColors.warn
            : AppColors.alert;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2.5),
      child: Row(
        children: [
          SizedBox(
            width: 18,
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 9,
                color: AppColors.textMute,
                letterSpacing: 1.0,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: SizedBox(
              height: 3,
              child: Stack(
                children: [
                  Container(color: AppColors.panel3),
                  FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: health,
                    child: Container(color: barColor),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 30,
            child: Text(
              '${(health * 100).round()}%',
              textAlign: TextAlign.right,
              style: AppText.dataSmall
                  .copyWith(fontSize: 9.5, color: AppColors.textDim),
            ),
          ),
        ],
      ),
    );
  }
}

class _QuadPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final centers = [
      Offset(w * 0.22, h * 0.25),
      Offset(w * 0.78, h * 0.25),
      Offset(w * 0.22, h * 0.78),
      Offset(w * 0.78, h * 0.78),
    ];
    final lines = Paint()
      ..color = AppColors.line2
      ..strokeWidth = 1;
    canvas.drawLine(centers[0], centers[3], lines);
    canvas.drawLine(centers[1], centers[2], lines);

    final fill = Paint()..color = AppColors.panel2;
    final stroke = Paint()
      ..color = AppColors.lineStrong
      ..style = PaintingStyle.stroke;

    for (int i = 0; i < 4; i++) {
      canvas.drawCircle(centers[i], 10, fill);
      canvas.drawCircle(centers[i], 10, stroke);
      // tiny direction tick
      final tick = Paint()
        ..color = AppColors.text
        ..strokeWidth = 1.2;
      canvas.drawLine(centers[i], centers[i] + const Offset(0, -6), tick);
    }

    // chassis center
    canvas.drawRect(
      Rect.fromCenter(center: Offset(w / 2, h / 2), width: 14, height: 14),
      Paint()..color = AppColors.panel3,
    );
    canvas.drawRect(
      Rect.fromCenter(center: Offset(w / 2, h / 2), width: 14, height: 14),
      Paint()
        ..color = AppColors.lineStrong
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _QuadPainter oldDelegate) => false;
}

class _LidarPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final maxR = math.min(size.width, size.height) / 2 - 4;

    // Subtle radial gradient backdrop
    final bg = Paint()
      ..shader = RadialGradient(
        colors: [AppColors.panel2, AppColors.panel],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: maxR));
    canvas.drawCircle(Offset(cx, cy), maxR, bg);

    final ring = Paint()
      ..color = AppColors.line2
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.7;
    for (final r in [maxR, maxR * 0.66, maxR * 0.33]) {
      canvas.drawCircle(Offset(cx, cy), r, ring);
    }
    canvas.drawLine(Offset(cx, cy - maxR), Offset(cx, cy + maxR), ring);
    canvas.drawLine(Offset(cx - maxR, cy), Offset(cx + maxR, cy), ring);

    // Sweep — desaturated amber wedge
    final sweep = Paint()
      ..shader = RadialGradient(
        colors: [
          AppColors.accent.withOpacity(0.18),
          AppColors.accent.withOpacity(0),
        ],
      ).createShader(Rect.fromCircle(center: Offset(cx, cy), radius: maxR));
    final sweepPath = Path()
      ..moveTo(cx, cy)
      ..lineTo(cx, cy - maxR)
      ..arcToPoint(
        Offset(cx + maxR * 0.85, cy - maxR * 0.5),
        radius: Radius.circular(maxR),
      )
      ..close();
    canvas.drawPath(sweepPath, sweep);

    // Returns — small dots
    final rng = math.Random(7);
    final dot = Paint()..color = AppColors.text.withOpacity(0.65);
    for (int i = 0; i < 32; i++) {
      final a = rng.nextDouble() * 2 * math.pi;
      final r = (rng.nextDouble() * 0.8 + 0.1) * maxR;
      canvas.drawCircle(
        Offset(cx + math.cos(a) * r, cy + math.sin(a) * r),
        1.1,
        dot,
      );
    }

    // Center
    canvas.drawCircle(Offset(cx, cy), 2.2, Paint()..color = AppColors.accent);
  }

  @override
  bool shouldRepaint(covariant _LidarPainter oldDelegate) => false;
}
