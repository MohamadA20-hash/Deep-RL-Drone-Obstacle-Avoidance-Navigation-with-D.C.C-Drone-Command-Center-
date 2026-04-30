import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as ws_status;

import '../config/app_config.dart';
import '../models/telemetry.dart';

/// Connection lifecycle states surfaced to the UI footer.
enum WsConnectionState { disconnected, connecting, connected, error }

/// Decoded backend WebSocket envelope: `{type, message, data}`.
class WsEnvelope {
  final String type;
  final String? message;
  final dynamic data;
  const WsEnvelope({required this.type, this.message, this.data});

  factory WsEnvelope.fromJson(Map<String, dynamic> j) => WsEnvelope(
        type: (j['type'] as String?) ?? 'unknown',
        message: j['message'] as String?,
        data: j['data'],
      );
}

/// One sample on the live flight path. We keep only what the map needs.
class TrailPoint {
  final double north; // NED X
  final double east; // NED Y
  final double down; // NED Z
  final DateTime at;
  const TrailPoint(this.north, this.east, this.down, this.at);
}

/// Long-lived telemetry WebSocket client. Auto-reconnects with linear backoff
/// (capped at 10s) and re-subscribes to the active drone after reconnect.
///
/// In addition to the live telemetry [ValueNotifier]s, the service exposes:
///   * [lastFrameAt] — wall-clock of the most recent frame for any drone.
///     The dashboard uses this to decide whether AirSim is actually streaming.
///   * [trailFor] — a bounded ring buffer of recent NED positions for a drone,
///     used by the map to draw the flight trail.
class TelemetryWebSocketService {
  TelemetryWebSocketService({this.maxTrailPoints = 300});

  /// Maximum trail points retained per drone.
  final int maxTrailPoints;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _reconnectTimer;

  String? _activeDroneId;
  int _backoffMs = 1000;

  final ValueNotifier<WsConnectionState> connection =
      ValueNotifier<WsConnectionState>(WsConnectionState.disconnected);

  /// Wall-clock of the most recent telemetry frame received on any drone.
  /// `null` until the first frame arrives.
  final ValueNotifier<DateTime?> lastFrameAt = ValueNotifier<DateTime?>(null);

  /// Latest telemetry per droneId.
  final Map<String, ValueNotifier<Telemetry?>> _byDrone = {};

  /// Bounded NED trail per droneId (oldest first).
  final Map<String, ValueNotifier<List<TrailPoint>>> _trailByDrone = {};
  final Map<String, Queue<TrailPoint>> _trailBuffers = {};

  /// Last raw envelope (for debug / future use).
  final ValueNotifier<WsEnvelope?> lastEnvelope =
      ValueNotifier<WsEnvelope?>(null);

  ValueNotifier<Telemetry?> notifierFor(String droneId) =>
      _byDrone.putIfAbsent(droneId, () => ValueNotifier<Telemetry?>(null));

  ValueNotifier<List<TrailPoint>> trailFor(String droneId) => _trailByDrone
      .putIfAbsent(droneId, () => ValueNotifier<List<TrailPoint>>(const []));

  /// Clear the recorded trail for a drone (called when a new mission starts).
  void clearTrail(String droneId) {
    _trailBuffers[droneId]?.clear();
    final n = _trailByDrone[droneId];
    if (n != null) n.value = const [];
  }

  void connect() {
    if (connection.value == WsConnectionState.connecting ||
        connection.value == WsConnectionState.connected) {
      return;
    }
    _open();
  }

  void _open() {
    connection.value = WsConnectionState.connecting;
    try {
      final uri = Uri.parse(AppConfig.telemetryWsUrl);
      final ch = WebSocketChannel.connect(uri);
      _channel = ch;
      _sub = ch.stream.listen(
        _onMessage,
        onDone: _onClosed,
        onError: _onError,
        cancelOnError: false,
      );
      connection.value = WsConnectionState.connected;
      _backoffMs = 1000;
      // Re-subscribe on reconnect.
      if (_activeDroneId != null) {
        _send({'action': 'subscribe', 'droneId': _activeDroneId});
      }
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _onMessage(dynamic raw) {
    if (raw is! String) return;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      final env = WsEnvelope.fromJson(Map<String, dynamic>.from(decoded));
      lastEnvelope.value = env;
      if (env.type == 'telemetry' && env.data is Map) {
        final t =
            Telemetry.fromJson(Map<String, dynamic>.from(env.data as Map));
        if (t.droneId != null) {
          notifierFor(t.droneId!).value = t;
          lastFrameAt.value = DateTime.now();
          _appendTrail(t);
        }
      }
    } catch (_) {/* ignore malformed frame */}
  }

  void _appendTrail(Telemetry t) {
    final n = t.positionNedX;
    final e = t.positionNedY;
    final d = t.positionNedZ;
    if (n == null || e == null) return;
    final id = t.droneId!;
    final buf = _trailBuffers.putIfAbsent(id, () => Queue<TrailPoint>());
    // Skip duplicate points (bridge sometimes re-publishes the same frame).
    if (buf.isNotEmpty) {
      final last = buf.last;
      if ((last.north - n).abs() < 0.01 && (last.east - e).abs() < 0.01) {
        return;
      }
    }
    buf.addLast(TrailPoint(n, e, d ?? 0, t.timestamp ?? DateTime.now()));
    while (buf.length > maxTrailPoints) {
      buf.removeFirst();
    }
    trailFor(id).value = List<TrailPoint>.unmodifiable(buf);
  }

  void _onClosed() {
    connection.value = WsConnectionState.disconnected;
    _scheduleReconnect();
  }

  void _onError(Object _) {
    connection.value = WsConnectionState.error;
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(milliseconds: _backoffMs), () {
      _backoffMs = (_backoffMs * 2).clamp(1000, 10000);
      _open();
    });
  }

  /// Subscribe to telemetry for a given drone. Replaces any prior subscription.
  void subscribeToDrone(String droneId) {
    if (_activeDroneId == droneId) return;
    if (_activeDroneId != null) {
      _send({'action': 'unsubscribe', 'droneId': _activeDroneId});
    }
    _activeDroneId = droneId;
    _send({'action': 'subscribe', 'droneId': droneId});
  }

  /// Re-send the active subscription. Used as a watchdog when AirSim restarts:
  /// the backend may have dropped our subscription on the bridge-side reset,
  /// so the dashboard nudges it whenever it notices stale telemetry while the
  /// bridge process itself is alive.
  void resendSubscription() {
    final id = _activeDroneId;
    if (id == null) return;
    _send({'action': 'subscribe', 'droneId': id});
  }

  void _send(Map<String, dynamic> msg) {
    final ch = _channel;
    if (ch == null || connection.value != WsConnectionState.connected) return;
    try {
      ch.sink.add(jsonEncode(msg));
    } catch (_) {/* ignore */}
  }

  Future<void> dispose() async {
    _reconnectTimer?.cancel();
    await _sub?.cancel();
    try {
      await _channel?.sink.close(ws_status.normalClosure);
    } catch (_) {}
    for (final n in _byDrone.values) {
      n.dispose();
    }
    for (final n in _trailByDrone.values) {
      n.dispose();
    }
    _byDrone.clear();
    _trailByDrone.clear();
    _trailBuffers.clear();
    connection.dispose();
    lastEnvelope.dispose();
    lastFrameAt.dispose();
  }
}

final telemetryWsServiceProvider = Provider<TelemetryWebSocketService>((ref) {
  final svc = TelemetryWebSocketService();
  svc.connect();
  ref.onDispose(svc.dispose);
  return svc;
});
