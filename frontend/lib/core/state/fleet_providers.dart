import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/bridge_status.dart';
import '../models/drone.dart';
import '../models/telemetry.dart';
import '../repositories/bridge_repository.dart';
import '../repositories/drone_repository.dart';
import '../repositories/telemetry_repository.dart';
import '../services/telemetry_websocket_service.dart';

/// FutureProvider — full fleet roster from `/api/drones/all`.
/// UI gets `AsyncValue<List<Drone>>`.
final fleetProvider = FutureProvider<List<Drone>>((ref) async {
  final repo = ref.watch(droneRepositoryProvider);
  return repo.listAll();
});

/// Currently-selected drone id. Defaults to the first drone in the fleet
/// once the fleet has loaded (handled in `selectedDroneProvider`).
final selectedDroneIdProvider = StateProvider<String?>((_) => null);

/// Convenience: the currently-selected `Drone` (or null while loading).
final selectedDroneProvider = Provider<Drone?>((ref) {
  final fleet = ref.watch(fleetProvider).asData?.value;
  if (fleet == null || fleet.isEmpty) return null;
  final selectedId = ref.watch(selectedDroneIdProvider);
  if (selectedId == null) return fleet.first;
  return fleet.firstWhere((d) => d.id == selectedId, orElse: () => fleet.first);
});

/// Live telemetry for the selected drone, fed by:
///   1. an initial REST snapshot from `/api/telemetry/drone/{id}/latest`
///   2. ongoing WS pushes from the telemetry stream
///
/// Returns a `ValueListenable<Telemetry?>` that the UI can `ListenableBuilder`
/// on. Re-subscribes whenever the selected drone changes.
final liveTelemetryProvider = Provider<ValueListenable<Telemetry?>>((ref) {
  final ws = ref.watch(telemetryWsServiceProvider);
  final drone = ref.watch(selectedDroneProvider);
  if (drone == null) {
    return ws.notifierFor('__none__');
  }
  ws.subscribeToDrone(drone.id);
  final notifier = ws.notifierFor(drone.id);

  // Seed with the latest REST snapshot if we don't yet have a WS frame.
  if (notifier.value == null) {
    final repo = ref.read(telemetryRepositoryProvider);
    repo.getLatest(drone.id).then((t) {
      if (t != null && notifier.value == null) {
        notifier.value = t;
      }
    });
  }
  return notifier;
});

/// Exposes the WS connection state to status widgets (footer / topbar).
final wsConnectionProvider =
    Provider<ValueListenable<WsConnectionState>>((ref) {
  return ref.watch(telemetryWsServiceProvider).connection;
});

// ── AirSim bridge status ─────────────────────────────────────────────────
//
// The backend hosts a Python "auto-bridge" subprocess that talks to AirSim.
// We poll `/api/airsim-bridge/status` every 3 seconds so the UI can flip
// between OFFLINE / SEARCHING / ONLINE without requiring a page reload.

/// How often the dashboard re-polls the bridge status endpoint.
const Duration _kBridgePollInterval = Duration(seconds: 3);

/// How long after the last telemetry frame we still consider AirSim "live".
const Duration _kTelemetryFreshWindow = Duration(seconds: 6);

/// Raw bridge status, refreshed every [_kBridgePollInterval]. The first event
/// is `BridgeStatus.unknown()` so the footer never renders a stale value.
final bridgeStatusProvider = StreamProvider<BridgeStatus>((ref) {
  final repo = ref.watch(bridgeRepositoryProvider);
  final ctrl = StreamController<BridgeStatus>();
  Timer? timer;
  bool closed = false;

  Future<void> tick() async {
    if (closed) return;
    try {
      final s = await repo.getStatus();
      if (!closed) ctrl.add(s);
    } catch (_) {
      if (!closed) {
        ctrl.add(
            const BridgeStatus(status: 'unreachable', processAlive: false));
      }
    }
  }

  ctrl.add(BridgeStatus.unknown());
  // Kick a poll immediately, then on a recurring timer.
  Future.microtask(tick);
  timer = Timer.periodic(_kBridgePollInterval, (_) => tick());

  ref.onDispose(() {
    closed = true;
    timer?.cancel();
    ctrl.close();
  });
  return ctrl.stream;
});

/// Wall-clock of the last telemetry frame from any drone (null until first).
final lastTelemetryAtProvider = Provider<ValueListenable<DateTime?>>((ref) {
  return ref.watch(telemetryWsServiceProvider).lastFrameAt;
});

/// True iff AirSim is actively streaming telemetry. Authoritative source is
/// the WebSocket frame freshness — if frames have arrived inside the freshness
/// window, AirSim is by definition streaming. The bridge-status REST poll is
/// only used as a fallback "no frames yet but bridge process is alive" signal
/// so the UI can flip from OFFLINE → SEARCHING quickly.
///
/// Reactive to BOTH the lastFrameAt ValueNotifier (immediate flip on first
/// frame) AND a 1s timer (so stale-detection still fires when frames stop).
final airsimStreamingProvider = StreamProvider<bool>((ref) {
  final ws = ref.watch(telemetryWsServiceProvider);

  bool compute() {
    final last = ws.lastFrameAt.value;
    if (last == null) return false;
    return DateTime.now().difference(last) <= _kTelemetryFreshWindow;
  }

  final ctrl = StreamController<bool>();
  bool lastEmitted = false;
  DateTime? lastResubAt;

  void emit() {
    final v = compute();
    // Watchdog: if no fresh frames, nudge the WS — re-open the socket if
    // it died and re-send the subscription. Throttled to once every 5s.
    if (!v) {
      final now = DateTime.now();
      if (lastResubAt == null ||
          now.difference(lastResubAt!) >= const Duration(seconds: 5)) {
        lastResubAt = now;
        ws.connect(); // no-op if already connected/connecting
        ws.resendSubscription();
      }
    }
    if (v != lastEmitted) {
      lastEmitted = v;
      ctrl.add(v);
    }
  }

  // React immediately to telemetry frames arriving (don't wait for the timer).
  void onFrame() => emit();
  ws.lastFrameAt.addListener(onFrame);

  ctrl.add(false);
  final timer = Timer.periodic(const Duration(seconds: 1), (_) => emit());
  ref.onDispose(() {
    ws.lastFrameAt.removeListener(onFrame);
    timer.cancel();
    ctrl.close();
  });
  return ctrl.stream;
});

/// Coarser tri-state used by status pills. If telemetry is actively flowing
/// we report `online` regardless of the REST bridge-status poll — a live WS
/// stream is the strongest possible proof the bridge is up.
final bridgeUiStateProvider = Provider<BridgeUiState>((ref) {
  final streaming = ref.watch(airsimStreamingProvider).asData?.value ?? false;
  if (streaming) return BridgeUiState.online;
  final asyncStatus = ref.watch(bridgeStatusProvider);
  final status = asyncStatus.asData?.value;
  if (status == null || status.status == 'unknown') {
    return BridgeUiState.unknown;
  }
  if (!status.processAlive) return BridgeUiState.offline;
  return BridgeUiState.searching;
});

/// Bounded NED trail buffer for the currently-selected drone. Empty until the
/// drone publishes a telemetry frame with NED coordinates.
final liveTrailProvider = Provider<ValueListenable<List<TrailPoint>>>((ref) {
  final ws = ref.watch(telemetryWsServiceProvider);
  final drone = ref.watch(selectedDroneProvider);
  if (drone == null) return ws.trailFor('__none__');
  return ws.trailFor(drone.id);
});
