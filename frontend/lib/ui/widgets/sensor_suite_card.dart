import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/repositories/sensor_repository.dart';
import '../../core/state/fleet_providers.dart';
import '../theme.dart';
import 'panel_card.dart';

/// Live sensor suite for the currently selected drone.
///
/// Hits `GET /api/drones/{id}/sensors` and renders one row per sensor with
/// the latest reading. Refreshes every 2 s while mounted. All values are
/// **derived from the drone's most recent telemetry record** \u2014 no client-side
/// synthesis or dummy data.
class SensorSuiteCard extends ConsumerStatefulWidget {
  const SensorSuiteCard({super.key});

  @override
  ConsumerState<SensorSuiteCard> createState() => _SensorSuiteCardState();
}

class _SensorSuiteCardState extends ConsumerState<SensorSuiteCard> {
  Timer? _poll;
  String? _lastDroneId;
  List<SensorReading> _sensors = const [];
  Object? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _refresh());
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    final drone = ref.read(selectedDroneProvider);
    if (drone == null) {
      if (mounted && _sensors.isNotEmpty) {
        setState(() {
          _sensors = const [];
          _lastDroneId = null;
        });
      }
      return;
    }
    if (_loading) return;
    _loading = true;
    try {
      final repo = ref.read(sensorRepositoryProvider);
      final list = await repo.listForDrone(drone.id);
      if (!mounted) return;
      setState(() {
        _sensors = list;
        _lastDroneId = drone.id;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    } finally {
      _loading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final drone = ref.watch(selectedDroneProvider);
    if (drone?.id != _lastDroneId) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
    }

    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.panel2,
                  border: Border.all(color: AppColors.accent),
                ),
                child: const Text(
                  'SNS',
                  style: TextStyle(
                    fontSize: 9,
                    letterSpacing: 1.6,
                    color: AppColors.accent,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              const Text(
                'LIVE SENSOR SUITE',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  drone == null
                      ? '\u2014 NO DRONE SELECTED \u2014'
                      : '${drone.name.toUpperCase()} \u00b7 ${drone.serialNumber ?? drone.id}',
                  style: const TextStyle(
                    color: AppColors.textMute,
                    fontSize: 10,
                    letterSpacing: 1.2,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (_loading)
                const SizedBox(
                  width: 10,
                  height: 10,
                  child: CircularProgressIndicator(
                    strokeWidth: 1.4,
                    valueColor: AlwaysStoppedAnimation(AppColors.accent),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'Readings derived from the drone\'s most recent telemetry row \u2014 no synthesis.',
            style: TextStyle(
              color: AppColors.textMute,
              fontSize: 10,
              height: 1.4,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 12),
          if (drone == null)
            const _Empty(text: 'Select a drone to inspect its sensor suite.')
          else if (_error != null)
            _Empty(text: 'Failed to load sensors: $_error')
          else if (_sensors.isEmpty)
            const _Empty(
                text: 'No sensors registered for this drone yet. '
                    'Run the seeder or add them via the API.')
          else
            Column(
              children: [
                for (int i = 0; i < _sensors.length; i++) ...[
                  if (i > 0) const SizedBox(height: 8),
                  _SensorRow(s: _sensors[i]),
                ],
              ],
            ),
        ],
      ),
    );
  }
}

class _SensorRow extends StatelessWidget {
  final SensorReading s;
  const _SensorRow({required this.s});

  @override
  Widget build(BuildContext context) {
    final dotColor = !s.enabled
        ? AppColors.textMute
        : s.online
            ? AppColors.ok
            : AppColors.warn;
    final stateLabel = !s.enabled
        ? 'DISABLED'
        : s.online
            ? 'LIVE'
            : 'NO SIGNAL';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.panel2,
        border: Border.all(color: AppColors.line2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: dotColor,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                s.type,
                style: const TextStyle(
                  color: AppColors.text,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.4,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  s.model,
                  style: const TextStyle(
                    color: AppColors.textMute,
                    fontSize: 10,
                    letterSpacing: 0.8,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                stateLabel,
                style: TextStyle(
                  color: dotColor,
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              if (s.frequencyHz > 0)
                _MiniSpec('FREQ', '${s.frequencyHz.toStringAsFixed(0)} Hz'),
              if (s.rangeMeters > 0) ...[
                const SizedBox(width: 12),
                _MiniSpec('RANGE', '${s.rangeMeters.toStringAsFixed(0)} m'),
              ],
              if (s.readingAt != null) ...[
                const SizedBox(width: 12),
                _MiniSpec('LAST', _ago(s.readingAt!)),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 14,
            runSpacing: 4,
            children: [
              for (final entry in s.reading.entries)
                _ReadingChip(label: entry.key, value: _format(entry.value)),
            ],
          ),
        ],
      ),
    );
  }

  static String _format(dynamic v) {
    if (v == null) return '\u2014';
    if (v is double) return v.toStringAsFixed(v.abs() < 10 ? 3 : 2);
    if (v is num) return v.toString();
    return v.toString();
  }

  static String _ago(DateTime t) {
    final secs = DateTime.now().toUtc().difference(t.toUtc()).inSeconds;
    if (secs < 1) return 'now';
    if (secs < 60) return '${secs}s ago';
    final m = secs ~/ 60;
    if (m < 60) return '${m}m ago';
    final h = m ~/ 60;
    return '${h}h ago';
  }
}

class _MiniSpec extends StatelessWidget {
  final String label;
  final String value;
  const _MiniSpec(this.label, this.value);
  @override
  Widget build(BuildContext context) {
    return RichText(
      text: TextSpan(children: [
        TextSpan(
          text: '$label ',
          style: const TextStyle(
            color: AppColors.textMute,
            fontSize: 9,
            letterSpacing: 1.0,
          ),
        ),
        TextSpan(
          text: value,
          style: const TextStyle(
            color: AppColors.text,
            fontSize: 10,
            fontWeight: FontWeight.w600,
          ),
        ),
      ]),
    );
  }
}

class _ReadingChip extends StatelessWidget {
  final String label;
  final String value;
  const _ReadingChip({required this.label, required this.value});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.bg,
        border: Border.all(color: AppColors.line2),
      ),
      child: RichText(
        text: TextSpan(children: [
          TextSpan(
            text: '${label.toUpperCase()}  ',
            style: const TextStyle(
              color: AppColors.textMute,
              fontSize: 9,
              letterSpacing: 1.0,
              fontFamilyFallback: ['Consolas', 'monospace'],
            ),
          ),
          TextSpan(
            text: value,
            style: const TextStyle(
              color: AppColors.accent,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              fontFamilyFallback: ['Consolas', 'monospace'],
            ),
          ),
        ]),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  final String text;
  const _Empty({required this.text});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 18),
      decoration: BoxDecoration(
        color: AppColors.panel2,
        border: Border.all(color: AppColors.line2),
      ),
      child: Center(
        child: Text(
          text,
          style: const TextStyle(
            color: AppColors.textMute,
            fontSize: 11,
            letterSpacing: 0.6,
          ),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
