import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../auth/auth_controller.dart';
import '../models/telemetry.dart';

/// REST repository for `/api/telemetry`.
class TelemetryRepository {
  TelemetryRepository(this._client);
  final ApiClient _client;

  /// Latest telemetry snapshot for a drone, or null if none exists.
  Future<Telemetry?> getLatest(String droneId) async {
    try {
      final r = await _client.dio.get('/api/telemetry/drone/$droneId/latest');
      final d = _data(r);
      if (d is Map) {
        return Telemetry.fromJson(Map<String, dynamic>.from(d));
      }
    } on DioException {
      return null;
    }
    return null;
  }

  static dynamic _data(Response r) {
    final body = r.data;
    if (body is Map && body.containsKey('data')) return body['data'];
    return body;
  }
}

final telemetryRepositoryProvider = Provider<TelemetryRepository>((ref) {
  return TelemetryRepository(ref.watch(apiClientProvider));
});
