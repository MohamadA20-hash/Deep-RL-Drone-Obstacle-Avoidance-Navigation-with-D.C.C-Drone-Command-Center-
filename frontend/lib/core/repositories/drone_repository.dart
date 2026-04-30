import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../auth/auth_controller.dart';
import '../models/drone.dart';

/// REST repository for `/api/drones`.
class DroneRepository {
  DroneRepository(this._client);
  final ApiClient _client;

  /// Returns every registered drone (uses the unpaged `/all` endpoint).
  Future<List<Drone>> listAll() async {
    final r = await _client.dio.get('/api/drones/all');
    final data = _data(r);
    if (data is List) {
      return data
          .whereType<Map>()
          .map((m) => Drone.fromJson(Map<String, dynamic>.from(m)))
          .toList();
    }
    return const [];
  }

  Future<Drone?> getById(String id) async {
    try {
      final r = await _client.dio.get('/api/drones/$id');
      final d = _data(r);
      if (d is Map) {
        return Drone.fromJson(Map<String, dynamic>.from(d));
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

final droneRepositoryProvider = Provider<DroneRepository>((ref) {
  return DroneRepository(ref.watch(apiClientProvider));
});
