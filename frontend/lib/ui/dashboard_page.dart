import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/models/telemetry.dart';
import '../core/state/fleet_providers.dart';
import 'theme.dart';
import 'widgets/sidebar.dart';
import 'widgets/topbar.dart';
import 'widgets/left_column.dart';
import 'widgets/sim_world_map.dart';
import 'widgets/fpv_camera.dart';
import 'widgets/bead_metric.dart';
import 'widgets/footer.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: FittedBox(
          fit: BoxFit.contain,
          child: Container(
            width: 1480,
            height: 830,
            decoration: BoxDecoration(
              color: AppColors.bg,
              borderRadius: BorderRadius.circular(2),
            ),
            clipBehavior: Clip.antiAlias,
            child: const Row(
              children: [
                SidebarNav(),
                Expanded(child: _MainArea()),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MainArea extends StatelessWidget {
  const _MainArea();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.main,
      padding: const EdgeInsets.all(10),
      child: Column(
        children: [
          const Topbar(),
          const SizedBox(height: 10),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(width: 200, child: LeftColumn()),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    children: [
                      const Expanded(flex: 5, child: SimWorldMap()),
                      const SizedBox(height: 12),
                      Expanded(
                        flex: 3,
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: const [
                            Expanded(flex: 3, child: FpvCamera()),
                            SizedBox(width: 12),
                            Expanded(flex: 2, child: _LiveBeadMetrics()),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          const FooterBar(),
        ],
      ),
    );
  }
}

/// Speed + altitude bead meters wired to live telemetry.
class _LiveBeadMetrics extends ConsumerWidget {
  const _LiveBeadMetrics();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final telemetryListenable = ref.watch(liveTelemetryProvider);
    final live = ref.watch(airsimStreamingProvider).asData?.value ?? false;
    return ValueListenableBuilder<Telemetry?>(
      valueListenable: telemetryListenable,
      builder: (context, tRaw, _) {
        const maxSpeed = 10.0;
        const maxAlt = 50.0;
        // When AirSim isn't streaming we discard the telemetry value so the
        // beads honestly read 0 instead of a stale snapshot.
        final t = live ? tRaw : null;
        final speed = t == null ? 0.0 : (t.navrlSpeed ?? t.groundSpeed);
        final alt = t?.altitude ?? 0;
        return Column(
          children: [
            Expanded(
              child: BeadMetricCard(
                title: 'SPEED',
                icon: Icons.speed,
                value: '${speed.toStringAsFixed(2)} m/s',
                percent: (speed / maxSpeed).clamp(0.0, 1.0),
                min: '0',
                max: maxSpeed.toStringAsFixed(0),
              ),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: BeadMetricCard(
                title: 'ALTITUDE',
                icon: Icons.height,
                value: '${alt.toStringAsFixed(2)} m',
                percent: (alt / maxAlt).clamp(0.0, 1.0),
                min: '0',
                max: maxAlt.toStringAsFixed(0),
              ),
            ),
          ],
        );
      },
    );
  }
}
