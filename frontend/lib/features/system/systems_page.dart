import 'dart:collection';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/state/fleet_providers.dart';
import '../../ui/theme.dart';
import '../../ui/widgets/app_shell.dart';
import '../../ui/widgets/panel_card.dart';
import '../../ui/widgets/sensor_suite_card.dart';

/// SYSTEMS view.
///
/// Mirrors the components mounted on the Fusion 360 airframe model and
/// gives each subsystem its own card with a rolling sparkline of its key
/// metric. Numeric values are synthesised on-device from a small
/// deterministic oscillator (wall-clock keyed) so the readouts breathe in
/// realistic engineering ranges without faking telemetry that would mislead
/// an operator. Motor RPMs / EKF state collapse to zero / STANDBY when
/// AirSim isn't streaming.
class SystemsPage extends ConsumerStatefulWidget {
  const SystemsPage({super.key});

  @override
  ConsumerState<SystemsPage> createState() => _SystemsPageState();
}

class _SystemsPageState extends ConsumerState<SystemsPage>
    with SingleTickerProviderStateMixin {
  static const int _kHistory = 120; // ~12 s @ 10 Hz
  late final Ticker _ticker = createTicker(_onTick);
  double _t = 0;
  double _lastT = -1;

  // Rolling histories per metric.
  final Queue<double> _jetsonTemp = Queue<double>();
  final Queue<double> _gpuLoad = Queue<double>();
  final Queue<double> _vib = Queue<double>();
  final Queue<double> _lidarKpts = Queue<double>();
  final Queue<double> _rpmAvg = Queue<double>();

  @override
  void initState() {
    super.initState();
    _ticker.start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  void _onTick(Duration d) {
    final s = d.inMilliseconds / 1000.0;
    if ((s - _lastT).abs() < 0.1) return;
    _lastT = s;
    _t = s;
    final live = ref.read(airsimStreamingProvider).asData?.value ?? false;
    _push(_jetsonTemp, _jetsonTempC());
    _push(_gpuLoad, _jetsonGpuPct());
    _push(_vib, _vibRms());
    _push(_lidarKpts, live ? _lidarKptsRaw().toDouble() : 0);
    final rpms = _rpms(live);
    _push(_rpmAvg, rpms.fold(0, (a, b) => a + b) / 4.0);
    if (mounted) setState(() {});
  }

  void _push(Queue<double> q, double v) {
    q.addLast(v);
    while (q.length > _kHistory) {
      q.removeFirst();
    }
  }

  // ---- Synthesised readouts (same shape as left-column hardware panel) ----
  double _jetsonTempC() =>
      52.0 + 6.0 * math.sin(_t * 0.6) + 1.4 * math.sin(_t * 4.1);
  double _jetsonGpuPct() =>
      38.0 + 12.0 * math.sin(_t * 0.45 + 1.1) + 4.0 * math.sin(_t * 3.3);
  double _jetsonRamGb() => 6.4 + 0.6 * math.sin(_t * 0.3 + 2.0);
  int _jetsonPowerW() => (12 + 3 * math.sin(_t * 0.55)).round();

  double _imuBiasMdps() => 8.0 + 3.0 * math.sin(_t * 0.9 + 0.3).abs();
  double _vibRms() => 0.42 + 0.08 * math.sin(_t * 1.2).abs();

  int _lidarKptsRaw() => (200 + 18 * math.sin(_t * 0.7)).round();
  double _lidarNoiseMm() => 18.0 + 2.5 * math.sin(_t * 1.4);
  int _lidarFovPct() => (94 + 4 * math.sin(_t * 0.5).abs()).round();

  List<int> _rpms(bool live) {
    if (!live) return [0, 0, 0, 0];
    final base = 3500 + 220 * math.sin(_t * 0.4);
    return [
      (base + 60 * math.sin(_t * 1.1 + 0.0)).round(),
      (base + 60 * math.sin(_t * 1.1 + 1.6)).round(),
      (base + 60 * math.sin(_t * 1.1 + 3.1)).round(),
      (base + 60 * math.sin(_t * 1.1 + 4.7)).round(),
    ];
  }

  double _escTempC() => 36.0 + 4.0 * math.sin(_t * 0.8);

  @override
  Widget build(BuildContext context) {
    final live = ref.watch(airsimStreamingProvider).asData?.value ?? false;
    final drone = ref.watch(selectedDroneProvider);
    final rpms = _rpms(live);

    return AppShell(
      activeRoute: 'systems',
      title: 'Systems',
      subtitle:
          'Airframe // Fusion 360 model // ${drone?.name.toUpperCase() ?? '— NO DRONE —'}',
      trailing: _LiveBadge(on: live),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _IntroBanner(live: live),
            const SizedBox(height: 12),
            const SensorSuiteCard(),
            const SizedBox(height: 12),
            // Top row: compute + flight controller
            LayoutBuilder(builder: (ctx, c) {
              final wide = c.maxWidth > 980;
              if (wide) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _jetsonCard()),
                    const SizedBox(width: 12),
                    Expanded(child: _pixhawkCard(live)),
                  ],
                );
              }
              return Column(children: [
                _jetsonCard(),
                const SizedBox(height: 12),
                _pixhawkCard(live),
              ]);
            }),
            const SizedBox(height: 12),
            // Bottom row: lidar + propulsion
            LayoutBuilder(builder: (ctx, c) {
              final wide = c.maxWidth > 980;
              if (wide) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _lidarCard(live)),
                    const SizedBox(width: 12),
                    Expanded(child: _propulsionCard(live, rpms)),
                  ],
                );
              }
              return Column(children: [
                _lidarCard(live),
                const SizedBox(height: 12),
                _propulsionCard(live, rpms),
              ]);
            }),
            const SizedBox(height: 12),
            _BomCard(),
          ],
        ),
      ),
    );
  }

  // -------------- Card builders --------------

  Widget _jetsonCard() => _SubsystemCard(
        tag: 'CMP',
        title: 'JETSON ORIN NX',
        spec: '16 GB LPDDR5 // 100 TOPS AI',
        status: 'NOMINAL',
        rows: [
          _Stat('SoC TEMP', '${_jetsonTempC().toStringAsFixed(1)} \u00b0C'),
          _Stat('GPU LOAD', '${_jetsonGpuPct().toStringAsFixed(0)}%'),
          _Stat('RAM USED', '${_jetsonRamGb().toStringAsFixed(1)} / 16 GB'),
          _Stat('PWR DRAW', '${_jetsonPowerW()} W'),
          _Stat('CUDA', '12.4 / TRT 10.0'),
          _Stat('UPTIME', _uptime()),
        ],
        sparkLabel: 'SoC TEMP \u00b0C',
        sparkData: _jetsonTemp.toList(),
        sparkMin: 40,
        sparkMax: 75,
        sparkColor: AppColors.accent,
      );

  Widget _pixhawkCard(bool live) => _SubsystemCard(
        tag: 'FCU',
        title: 'PIXHAWK 6X',
        spec: 'STM32H753 // PX4 v1.14',
        status: live ? 'CONVERGED' : 'STANDBY',
        rows: [
          _Stat('EKF STATE', live ? 'CONVERGED' : 'STANDBY'),
          _Stat('IMU BIAS', '${_imuBiasMdps().toStringAsFixed(1)} m\u00b0/s'),
          _Stat('VIB RMS', '${_vibRms().toStringAsFixed(2)} m/s\u00b2'),
          _Stat('MAG HEALTH', live ? 'OK' : '\u2014'),
          _Stat('GPS FIX', live ? '3D / RTK FLOAT' : 'NO FIX'),
          _Stat('LOOP RATE', '400 Hz'),
        ],
        sparkLabel: 'AIRFRAME VIB m/s\u00b2',
        sparkData: _vib.toList(),
        sparkMin: 0,
        sparkMax: 0.8,
        sparkColor: AppColors.warn,
      );

  Widget _lidarCard(bool live) => _SubsystemCard(
        tag: 'LDR',
        title: 'LIVOX MID-360',
        spec: '360\u00b0 horizontal // 40 m range',
        status: live ? 'SCANNING' : 'IDLE',
        rows: [
          _Stat('RETURN RATE', live ? '${_lidarKptsRaw()} kpt/s' : '\u2014'),
          _Stat('NOISE \u03c3', '${_lidarNoiseMm().toStringAsFixed(1)} mm'),
          _Stat('FOV UTIL', '${_lidarFovPct()}%'),
          _Stat('FREQ', '10 Hz'),
          _Stat('LASER CLASS', 'Class 1 / 905 nm'),
          _Stat('MOUNT', 'TOP / +Z'),
        ],
        sparkLabel: 'POINT RETURNS kpt/s',
        sparkData: _lidarKpts.toList(),
        sparkMin: 0,
        sparkMax: 240,
        sparkColor: AppColors.accent,
      );

  Widget _propulsionCard(bool live, List<int> rpms) => _SubsystemCard(
        tag: 'PRP',
        title: 'T-MOTOR F90 \u00d74',
        spec: 'BLDC 1300 KV // 30 A ESC // 12\" prop',
        status: live ? 'ARMED' : 'DISARMED',
        rows: [
          _Stat('M1', '${rpms[0]} rpm'),
          _Stat('M2', '${rpms[1]} rpm'),
          _Stat('M3', '${rpms[2]} rpm'),
          _Stat('M4', '${rpms[3]} rpm'),
          _Stat('ESC TEMP', '${_escTempC().toStringAsFixed(1)} \u00b0C'),
          _Stat('THRUST', live ? '~16.4 N (hover)' : '0 N'),
        ],
        sparkLabel: 'AVG RPM',
        sparkData: _rpmAvg.toList(),
        sparkMin: 0,
        sparkMax: 5000,
        sparkColor: AppColors.accent,
      );

  String _uptime() {
    final s = _t.toInt();
    final h = s ~/ 3600;
    final m = (s % 3600) ~/ 60;
    final ss = s % 60;
    return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${ss.toString().padLeft(2, '0')}';
  }
}

// ============================================================
// Building blocks
// ============================================================

class _IntroBanner extends StatelessWidget {
  final bool live;
  const _IntroBanner({required this.live});
  @override
  Widget build(BuildContext context) {
    return PanelCard(
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.panel2,
              border: Border.all(color: AppColors.line2),
            ),
            child: const Text(
              'CAD // FUSION 360',
              style: TextStyle(
                fontSize: 9,
                letterSpacing: 1.6,
                color: AppColors.accent,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Text(
              'Airframe components mirrored from the as-built CAD model. '
              'Telemetry below is synthesised in-app from a deterministic '
              'oscillator and is not a hardware bus reading.',
              style: TextStyle(
                color: AppColors.textMute,
                fontSize: 11,
                height: 1.45,
                letterSpacing: 0.4,
              ),
            ),
          ),
          const SizedBox(width: 12),
          StatusBadge(
              text: live ? 'AIRSIM LIVE' : 'AIRSIM IDLE',
              color: live ? AppColors.accent : AppColors.textMute),
        ],
      ),
    );
  }
}

class _Stat {
  final String k;
  final String v;
  const _Stat(this.k, this.v);
}

class _SubsystemCard extends StatelessWidget {
  final String tag;
  final String title;
  final String spec;
  final String status;
  final List<_Stat> rows;
  final String sparkLabel;
  final List<double> sparkData;
  final double sparkMin;
  final double sparkMax;
  final Color sparkColor;

  const _SubsystemCard({
    required this.tag,
    required this.title,
    required this.spec,
    required this.status,
    required this.rows,
    required this.sparkLabel,
    required this.sparkData,
    required this.sparkMin,
    required this.sparkMax,
    required this.sparkColor,
  });

  @override
  Widget build(BuildContext context) {
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.panel2,
                  border: Border.all(color: AppColors.line2),
                ),
                child: Text(
                  tag,
                  style: const TextStyle(
                    fontSize: 9.5,
                    letterSpacing: 1.6,
                    color: AppColors.accent,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: AppText.cardTitle),
                    const SizedBox(height: 2),
                    Text(spec, style: AppText.cardSub),
                  ],
                ),
              ),
              StatusBadge(text: status, color: AppColors.accent),
            ],
          ),
          const SizedBox(height: 12),
          // Stat grid (two columns)
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            childAspectRatio: 5.5,
            mainAxisSpacing: 2,
            crossAxisSpacing: 16,
            children: rows.map((r) => _StatRow(k: r.k, v: r.v)).toList(),
          ),
          const SizedBox(height: 14),
          // Sparkline
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(sparkLabel,
                  style: const TextStyle(
                    fontSize: 9,
                    letterSpacing: 1.6,
                    color: AppColors.textMute,
                    fontWeight: FontWeight.w600,
                  )),
              Text(
                sparkData.isEmpty ? '—' : sparkData.last.toStringAsFixed(1),
                style: AppText.dataSmall,
              ),
            ],
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 60,
            child: CustomPaint(
              painter: _SparkPainter(
                data: sparkData,
                min: sparkMin,
                max: sparkMax,
                color: sparkColor,
              ),
              child: const SizedBox.expand(),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatRow extends StatelessWidget {
  final String k;
  final String v;
  const _StatRow({required this.k, required this.v});
  @override
  Widget build(BuildContext context) {
    return Row(
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
    );
  }
}

class _SparkPainter extends CustomPainter {
  final List<double> data;
  final double min;
  final double max;
  final Color color;
  _SparkPainter({
    required this.data,
    required this.min,
    required this.max,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Background grid
    final grid = Paint()
      ..color = AppColors.line2
      ..strokeWidth = 0.6;
    for (int i = 1; i < 4; i++) {
      final y = size.height * i / 4;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      Paint()
        ..color = AppColors.line2
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.8,
    );

    if (data.length < 2) return;
    final span = (max - min).abs() < 1e-6 ? 1.0 : (max - min);
    final stepX = size.width / (data.length - 1);
    final path = Path();
    for (int i = 0; i < data.length; i++) {
      final v = data[i].clamp(min, max);
      final x = stepX * i;
      final y = size.height - ((v - min) / span) * size.height;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    final stroke = Paint()
      ..color = color
      ..strokeWidth = 1.4
      ..style = PaintingStyle.stroke;
    canvas.drawPath(path, stroke);

    // Soft fill below the line
    final fillPath = Path.from(path)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(
      fillPath,
      Paint()..color = color.withOpacity(0.08),
    );
  }

  @override
  bool shouldRepaint(covariant _SparkPainter oldDelegate) =>
      oldDelegate.data != data ||
      oldDelegate.min != min ||
      oldDelegate.max != max;
}

class _BomCard extends StatelessWidget {
  static const _items = [
    [
      'CMP',
      'Jetson Orin NX 16 GB',
      'NVIDIA',
      'Companion compute / NavRL inference'
    ],
    ['FCU', 'Pixhawk 6X', 'Holybro', 'Flight controller (PX4)'],
    [
      'LDR',
      'Livox Mid-360',
      'Livox',
      '360\u00b0 LiDAR for obstacle perception'
    ],
    ['PRP', 'T-Motor F90 \u00d74', 'T-Motor', 'BLDC propulsion, 30 A ESCs'],
    ['BAT', '6S Li-ion 12 Ah', 'Tattu', 'Primary power'],
    [
      'FRM',
      'Carbon X-frame 500 mm',
      'Custom (Fusion 360)',
      'As-built airframe'
    ],
  ];

  @override
  Widget build(BuildContext context) {
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('BILL OF MATERIALS', style: AppText.cardTitle),
          const SizedBox(height: 4),
          const Text('From CAD assembly', style: AppText.cardSub),
          const SizedBox(height: 12),
          Container(height: 1, color: AppColors.line),
          for (final r in _items) ...[
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 7),
              child: Row(
                children: [
                  SizedBox(
                    width: 38,
                    child: Text(r[0],
                        style: const TextStyle(
                          fontSize: 9.5,
                          letterSpacing: 1.4,
                          color: AppColors.accent,
                          fontWeight: FontWeight.w700,
                        )),
                  ),
                  Expanded(
                    flex: 3,
                    child: Text(r[1], style: AppText.dataSmall),
                  ),
                  Expanded(
                    flex: 2,
                    child: Text(r[2],
                        style: const TextStyle(
                          fontSize: 10,
                          color: AppColors.textMute,
                          letterSpacing: 0.6,
                        )),
                  ),
                  Expanded(
                    flex: 4,
                    child: Text(r[3],
                        style: const TextStyle(
                          fontSize: 10,
                          color: AppColors.textDim,
                          letterSpacing: 0.4,
                        )),
                  ),
                ],
              ),
            ),
            Container(height: 1, color: AppColors.line),
          ],
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
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: on ? AppColors.accent.withOpacity(0.12) : AppColors.panel2,
        border: Border.all(
            color: on ? AppColors.accent : AppColors.line2, width: 1),
      ),
      child: Text(
        on ? 'AIRSIM LIVE' : 'AIRSIM IDLE',
        style: TextStyle(
          fontSize: 9.5,
          letterSpacing: 1.6,
          fontWeight: FontWeight.w700,
          color: on ? AppColors.accent : AppColors.textMute,
        ),
      ),
    );
  }
}
