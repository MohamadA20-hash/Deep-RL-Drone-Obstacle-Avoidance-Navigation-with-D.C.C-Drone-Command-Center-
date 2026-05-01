import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/models/bridge_status.dart';
import '../../core/services/telemetry_websocket_service.dart';
import '../../core/state/fleet_providers.dart';
import '../theme.dart';
import 'panel_card.dart';

/// Application version shown in the footer. Bump on each demo release.
const String kAppVersion = 'v1.0.0-demo';

class FooterBar extends ConsumerStatefulWidget {
  const FooterBar({super.key});

  @override
  ConsumerState<FooterBar> createState() => _FooterBarState();
}

class _FooterBarState extends ConsumerState<FooterBar> {
  late final Stream<DateTime> _clock = Stream<DateTime>.periodic(
    const Duration(seconds: 1),
    (_) => DateTime.now().toUtc(),
  );

  @override
  Widget build(BuildContext context) {
    final wsListenable = ref.watch(wsConnectionProvider);
    final fleet = ref.watch(fleetProvider);
    final selected = ref.watch(selectedDroneProvider);
    final bridge = ref.watch(bridgeUiStateProvider);

    return Container(
      padding: const EdgeInsets.fromLTRB(4, 8, 4, 4),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.line, width: 1)),
      ),
      child: ValueListenableBuilder<WsConnectionState>(
        valueListenable: wsListenable,
        builder: (context, wsState, _) {
          final ws = switch (wsState) {
            WsConnectionState.connected => _S.ok,
            WsConnectionState.connecting => _S.warn,
            _ => _S.alert,
          };
          final droneCount = fleet.asData?.value.length ?? 0;
          // CTRL availability tracks AirSim — without a live bridge we are
          // not authoritatively connected to any vehicle.
          final ctrlState = selected == null
              ? _S.alert
              : switch (bridge) {
                  BridgeUiState.online => _S.ok,
                  BridgeUiState.searching => _S.warn,
                  _ => _S.alert,
                };
          final airsimState = switch (bridge) {
            BridgeUiState.online => _S.ok,
            BridgeUiState.searching => _S.warn,
            BridgeUiState.unknown => _S.warn,
            BridgeUiState.offline => _S.alert,
          };
          final airsimLabel = switch (bridge) {
            BridgeUiState.online => 'AIRSIM\u00a0/\u00a0ONLINE',
            BridgeUiState.searching => 'AIRSIM\u00a0/\u00a0SEARCHING…',
            BridgeUiState.unknown => 'AIRSIM\u00a0/\u00a0…',
            BridgeUiState.offline => 'AIRSIM\u00a0/\u00a0OFFLINE',
          };
          final bridgeLabel = switch (bridge) {
            BridgeUiState.online => 'BRIDGE\u00a0/\u00a0STREAM',
            BridgeUiState.searching => 'BRIDGE\u00a0/\u00a0SEARCH',
            _ => 'BRIDGE\u00a0/\u00a0IDLE',
          };
          final ctrlLabel =
              'CTRL\u00a0/\u00a0${(selected?.name ?? '—').toUpperCase()}';

          return Row(
            children: [
              Expanded(
                child: Wrap(
                  spacing: 22,
                  runSpacing: 4,
                  children: [
                    _FootItem(text: airsimLabel, state: airsimState),
                    _FootItem(text: 'WS', state: ws),
                    _FootItem(text: ctrlLabel, state: ctrlState),
                    _FootItem(
                        text: 'NODES\u00a0/\u00a0$droneCount',
                        state: droneCount > 0 ? _S.ok : _S.warn),
                    _FootItem(text: bridgeLabel, state: airsimState),
                    const _FootItem(
                        text: 'CLASS\u00a0/\u00a0FOUO', state: _S.warn),
                    const _FootItem(
                        text: 'BUILD\u00a0/\u00a0$kAppVersion', state: _S.ok),
                  ],
                ),
              ),
              StreamBuilder<DateTime>(
                stream: _clock,
                initialData: DateTime.now().toUtc(),
                builder: (_, snap) {
                  final t = snap.data!;
                  String pad(int n) => n.toString().padLeft(2, '0');
                  return Text(
                    '${pad(t.hour)}:${pad(t.minute)}:${pad(t.second)}Z',
                    style: const TextStyle(
                      color: AppColors.textDim,
                      fontSize: 10,
                      letterSpacing: 1.2,
                      fontFamilyFallback: ['Consolas', 'monospace'],
                    ),
                  );
                },
              ),
            ],
          );
        },
      ),
    );
  }
}

enum _S { ok, warn, alert }

class _FootItem extends StatelessWidget {
  final String text;
  final _S state;
  const _FootItem({required this.text, this.state = _S.ok});

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      _S.ok => AppColors.ok,
      _S.warn => AppColors.warn,
      _S.alert => AppColors.alert,
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        StatusDot(color: color, size: 5),
        const SizedBox(width: 7),
        Text(text,
            style: const TextStyle(
              color: AppColors.textDim,
              fontSize: 9.5,
              letterSpacing: 1.4,
              fontWeight: FontWeight.w500,
            )),
      ],
    );
  }
}
