import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/auth/auth_controller.dart';
import '../../core/models/drone.dart';
import '../../core/models/telemetry.dart';
import '../../core/notifications/notification_center.dart';
import '../../core/services/telemetry_websocket_service.dart';
import '../../core/state/fleet_providers.dart';
import '../theme.dart';
import 'panel_card.dart';

class Topbar extends ConsumerStatefulWidget {
  const Topbar({super.key});

  @override
  ConsumerState<Topbar> createState() => _TopbarState();
}

class _TopbarState extends ConsumerState<Topbar> {
  /// Wall-clock origin used to render an approximate flight time when the
  /// backend hasn't yet provided one. Resets when the selected drone changes.
  DateTime? _flightStart;
  String? _lastDroneId;

  @override
  Widget build(BuildContext context) {
    final drone = ref.watch(selectedDroneProvider);
    final telemetryListenable = ref.watch(liveTelemetryProvider);
    final wsListenable = ref.watch(wsConnectionProvider);
    // Gate every metric on whether AirSim is actually streaming. Without a
    // live bridge we display 0 / OFFLINE / — instead of stale DB values.
    final live = ref.watch(airsimStreamingProvider).asData?.value ?? false;

    if (drone?.id != _lastDroneId) {
      _lastDroneId = drone?.id;
      _flightStart = DateTime.now();
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(2),
        border: Border.all(color: AppColors.line, width: 1),
      ),
      child: SizedBox(
        height: 50,
        child: ValueListenableBuilder<Telemetry?>(
          valueListenable: telemetryListenable,
          builder: (context, telemetry, _) {
            return Row(
              children: [
                Container(
                  width: 50,
                  height: 50,
                  decoration: BoxDecoration(
                    color: AppColors.panel2,
                    border: Border.all(color: AppColors.line2, width: 1),
                  ),
                  child:
                      const Icon(Icons.flight, color: AppColors.text, size: 20),
                ),
                const SizedBox(width: 12),
                _VehicleId(drone: drone),
                const SizedBox(width: 18),
                const _Divider(),
                Expanded(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      _Metric(label: 'COORD', value: _coord(telemetry, live)),
                      const _Divider(),
                      _Metric(
                          label: 'HDG',
                          value: _heading(telemetry, live),
                          mono: true),
                      const _Divider(),
                      _Metric(
                          label: 'SPD',
                          value: _speed(telemetry, live),
                          mono: true),
                      const _Divider(),
                      _Metric(
                          label: 'ALT',
                          value: _altitude(telemetry, live),
                          mono: true),
                      const _Divider(),
                      _Metric(
                          label: 'BAT',
                          value: _battery(telemetry, live),
                          mono: true),
                      const _Divider(),
                      _Metric(
                          label: 'GOAL',
                          value: _goal(telemetry, live),
                          mono: true),
                      const _Divider(),
                      _Metric(
                          label: 'FT', value: _flightTime(live), mono: true),
                    ],
                  ),
                ),
                const _Divider(),
                const SizedBox(width: 14),
                _LinkStatus(connection: wsListenable),
                const SizedBox(width: 14),
                const _Divider(),
                const SizedBox(width: 14),
                const NotificationBell(),
                const SizedBox(width: 14),
                const _Divider(),
                const SizedBox(width: 14),
                _OperatorPanel(
                  username: ref.watch(authControllerProvider).user?.username,
                  onLogout: () async {
                    await ref.read(authControllerProvider.notifier).logout();
                    if (context.mounted) context.go('/login');
                  },
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  // --- formatters -----------------------------------------------------------
  // All formatters return AirSim-honest values. When [live] is false the
  // bridge is not actively streaming, so we display OFFLINE / 0 / — rather
  // than the last-seen value from the database.

  String _coord(Telemetry? t, bool live) {
    if (!live || t == null) return 'OFFLINE';
    final lat = t.latitude;
    final lon = t.longitude;
    if (lat == 0 && lon == 0) return '0.0000°N\n0.0000°E';
    final ns = lat >= 0 ? 'N' : 'S';
    final ew = lon >= 0 ? 'E' : 'W';
    return '${lat.abs().toStringAsFixed(4)}°$ns\n${lon.abs().toStringAsFixed(4)}°$ew';
  }

  String _heading(Telemetry? t, bool live) {
    if (!live || t == null) return '—';
    return '${t.headingDeg.round().toString().padLeft(3, '0')}°';
  }

  String _speed(Telemetry? t, bool live) {
    if (!live || t == null) return '0.00 m/s';
    final s = t.navrlSpeed ?? t.groundSpeed;
    return '${s.toStringAsFixed(2)} m/s';
  }

  String _altitude(Telemetry? t, bool live) {
    if (!live || t == null) return '0.00 m';
    return '${t.altitude.toStringAsFixed(2)} m';
  }

  String _battery(Telemetry? t, bool live) {
    if (!live || t == null) return '0%';
    return '${t.batteryLevel.round()}%';
  }

  String _goal(Telemetry? t, bool live) {
    if (!live || t == null || t.distanceToGoal == null) return '—';
    return '${t.distanceToGoal!.toStringAsFixed(2)} m';
  }

  String _flightTime(bool live) {
    if (!live) return '00:00:00';
    final start = _flightStart;
    if (start == null) return '00:00:00';
    final elapsed = DateTime.now().difference(start);
    String pad(int n) => n.toString().padLeft(2, '0');
    return '${pad(elapsed.inHours)}:${pad(elapsed.inMinutes % 60)}:${pad(elapsed.inSeconds % 60)}';
  }
}

class _VehicleId extends StatelessWidget {
  final Drone? drone;
  const _VehicleId({required this.drone});

  @override
  Widget build(BuildContext context) {
    final name = drone?.name.toUpperCase() ?? '— NO DRONE —';
    final serial = drone?.serialNumber?.toUpperCase();
    final label = serial == null ? name : '$name // $serial';
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('VEHICLE',
            style: TextStyle(
              fontSize: 8.5,
              letterSpacing: 1.6,
              color: AppColors.textMute,
              fontWeight: FontWeight.w500,
            )),
        const SizedBox(height: 2),
        Text(label,
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.text,
              fontWeight: FontWeight.w600,
              letterSpacing: 1.0,
            )),
      ],
    );
  }
}

class _LinkStatus extends StatelessWidget {
  final ValueListenable<WsConnectionState> connection;
  const _LinkStatus({required this.connection});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<WsConnectionState>(
      valueListenable: connection,
      builder: (_, state, __) {
        final (label, color, sub) = switch (state) {
          WsConnectionState.connected => (
              'LINK',
              AppColors.ok,
              'WS  //  STREAM'
            ),
          WsConnectionState.connecting => (
              'LINK',
              AppColors.warn,
              'CONNECTING…'
            ),
          WsConnectionState.error => ('LINK', AppColors.alert, 'ERROR'),
          WsConnectionState.disconnected => (
              'LINK',
              AppColors.alert,
              'OFFLINE'
            ),
        };
        return Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            InlineStatus(text: label, color: color),
            const SizedBox(height: 4),
            Text(sub,
                style: const TextStyle(
                  fontSize: 9,
                  letterSpacing: 1.2,
                  color: AppColors.textMute,
                  fontWeight: FontWeight.w500,
                )),
          ],
        );
      },
    );
  }
}

class _OperatorPanel extends StatelessWidget {
  final String? username;
  final Future<void> Function() onLogout;
  const _OperatorPanel({required this.username, required this.onLogout});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('OPERATOR', style: AppText.label),
            const SizedBox(height: 3),
            Text(
              (username ?? 'GUEST').toUpperCase(),
              style: const TextStyle(
                fontSize: 11,
                letterSpacing: 1.4,
                color: AppColors.text,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        const SizedBox(width: 10),
        Tooltip(
          message: 'Sign out',
          child: Material(
            color: AppColors.panel2,
            child: InkWell(
              onTap: () => _confirmLogout(context),
              child: Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  border: Border.all(color: AppColors.line2, width: 1),
                ),
                alignment: Alignment.center,
                child: const Icon(Icons.logout,
                    size: 14, color: AppColors.textDim),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _confirmLogout(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      barrierColor: Colors.black.withOpacity(0.6),
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.panel,
        shape: RoundedRectangleBorder(
          side: const BorderSide(color: AppColors.line, width: 1),
          borderRadius: BorderRadius.circular(2),
        ),
        title: const Text('SIGN OUT',
            style: TextStyle(
              color: AppColors.text,
              fontSize: 12,
              letterSpacing: 2.4,
              fontWeight: FontWeight.w600,
            )),
        content: const Text(
          'End operator session and return to the sign-in screen?',
          style: TextStyle(color: AppColors.textDim, fontSize: 12),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('CANCEL',
                style: TextStyle(
                    color: AppColors.textMute,
                    fontSize: 10,
                    letterSpacing: 1.6)),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('SIGN OUT',
                style: TextStyle(
                    color: AppColors.alert,
                    fontSize: 10,
                    letterSpacing: 1.6,
                    fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
    if (ok == true) await onLogout();
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;
  final bool mono;
  const _Metric({required this.label, required this.value, this.mono = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppText.label),
          const SizedBox(height: 3),
          Text(value,
              style: mono
                  ? AppText.value
                  : const TextStyle(
                      fontSize: 11,
                      color: AppColors.text,
                      fontWeight: FontWeight.w500,
                      height: 1.2,
                      letterSpacing: 0.4,
                    )),
        ],
      ),
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();
  @override
  Widget build(BuildContext context) =>
      Container(width: 1, height: 32, color: AppColors.line);
}
