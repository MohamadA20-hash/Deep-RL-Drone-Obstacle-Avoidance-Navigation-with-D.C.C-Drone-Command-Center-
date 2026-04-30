import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../auth/auth_controller.dart';
import '../models/bridge_status.dart';

/// REST repository for `/api/airsim-bridge`.
class BridgeRepository {
  BridgeRepository(this._client);
  final ApiClient _client;

  /// Returns the current backend-reported bridge process status.
  /// Throws [DioException] on transport/auth failure.
  Future<BridgeStatus> getStatus() async {
    final r = await _client.dio.get('/api/airsim-bridge/status');
    final data = _data(r);
    if (data is Map) {
      return BridgeStatus.fromJson(Map<String, dynamic>.from(data));
    }
    return BridgeStatus.unknown();
  }

  /// Ask the backend to (re)start the bridge subprocess. Returns true if the
  /// backend reported success.
  Future<bool> startBridge() async {
    try {
      final r = await _client.dio.post('/api/airsim-bridge/start');
      final body = r.data;
      if (body is Map && body['success'] == true) return true;
      return r.statusCode != null && r.statusCode! < 300;
    } on DioException {
      return false;
    }
  }

  /// Ask the backend to fully restart the bridge subprocess.
  Future<bool> restartBridge() async {
    try {
      final r = await _client.dio.post('/api/airsim-bridge/restart');
      final body = r.data;
      if (body is Map && body['success'] == true) return true;
      return r.statusCode != null && r.statusCode! < 300;
    } on DioException {
      return false;
    }
  }

  /// Dispatch an autonomous-navigation goal in NED meters.
  ///
  /// Calls `POST /api/navrl/drones/{id}/start` which stores the goal on the
  /// drone, sets `flightStatus = NAVIGATING`, and persists a START_AUTONOMOUS_NAV
  /// command. The Python AirSim auto-bridge polls
  /// `GET /api/navrl/drones/{id}/status` every 3 s and, on seeing
  /// `isNavigating=true` with goal coords, spawns the `nav_worker` subprocess
  /// that drives AirSim along the planned A*+PPO path.
  Future<bool> startNavGoal({
    required String droneId,
    required double goalX,
    required double goalY,
    double baseAltitude = 5.0,
  }) async {
    try {
      final r = await _client.dio.post(
        '/api/navrl/drones/$droneId/start',
        data: {
          'goalX': goalX,
          'goalY': goalY,
          'baseAltitude': baseAltitude,
        },
      );
      return r.statusCode != null && r.statusCode! < 300;
    } on DioException {
      return false;
    }
  }

  /// Stop autonomous navigation for the given drone.
  Future<bool> stopNav(String droneId) async {
    try {
      final r = await _client.dio.post('/api/navrl/drones/$droneId/stop');
      return r.statusCode != null && r.statusCode! < 300;
    } on DioException {
      return false;
    }
  }

  /// Set (or update) the navigation goal in NED meters WITHOUT starting
  /// navigation. Calls `POST /api/navrl/drones/{id}/goal`. The drone stores
  /// the goal on its row; subsequent /start will use it.
  Future<bool> setGoal({
    required String droneId,
    required double goalX,
    required double goalY,
  }) async {
    try {
      final r = await _client.dio.post(
        '/api/navrl/drones/$droneId/goal',
        data: {'goalX': goalX, 'goalY': goalY},
      );
      return r.statusCode != null && r.statusCode! < 300;
    } on DioException {
      return false;
    }
  }

  /// Trigger an emergency landing. Stops any active navigation and lands
  /// the drone immediately. Calls `POST /api/navrl/drones/{id}/emergency-land`.
  Future<bool> emergencyLand(String droneId) async {
    try {
      final r =
          await _client.dio.post('/api/navrl/drones/$droneId/emergency-land');
      return r.statusCode != null && r.statusCode! < 300;
    } on DioException {
      return false;
    }
  }

  static dynamic _data(Response r) {
    final body = r.data;
    if (body is Map && body.containsKey('data')) return body['data'];
    return body;
  }
}

final bridgeRepositoryProvider = Provider<BridgeRepository>((ref) {
  return BridgeRepository(ref.watch(apiClientProvider));
});
