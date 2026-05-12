import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../auth/auth_controller.dart';

/// One sensor + its latest telemetry-derived reading.
class SensorReading {
  SensorReading({
    required this.id,
    required this.type,
    required this.model,
    required this.rangeMeters,
    required this.frequencyHz,
    required this.enabled,
    required this.online,
    required this.readingAt,
    required this.reading,
  });

  final String id;
  final String type; // GPS | IMU | LIDAR | CAMERA
  final String model;
  final double rangeMeters;
  final double frequencyHz;
  final bool enabled;
  final bool online;
  final DateTime? readingAt;
  final Map<String, dynamic> reading;

  factory SensorReading.fromJson(Map<String, dynamic> j) {
    return SensorReading(
      id: j['id']?.toString() ?? '',
      type: j['type']?.toString() ?? 'UNKNOWN',
      model: j['model']?.toString() ?? '',
      rangeMeters: (j['rangeMeters'] as num?)?.toDouble() ?? 0,
      frequencyHz: (j['frequencyHz'] as num?)?.toDouble() ?? 0,
      enabled: j['enabled'] == true,
      online: j['online'] == true,
      readingAt: j['readingAt'] != null
          ? DateTime.tryParse(j['readingAt'].toString())
          : null,
      reading: (j['reading'] as Map?)?.map(
            (k, v) => MapEntry(k.toString(), v),
          ) ??
          const {},
    );
  }
}

class SensorRepository {
  SensorRepository(this._client);
  final ApiClient _client;

  Future<List<SensorReading>> listForDrone(String droneId) async {
    final r = await _client.dio.get('/api/drones/$droneId/sensors');
    final body = r.data;
    final data =
        (body is Map && body.containsKey('data')) ? body['data'] : body;
    if (data is List) {
      return data
          .whereType<Map>()
          .map((m) => SensorReading.fromJson(Map<String, dynamic>.from(m)))
          .toList();
    }
    return const [];
  }
}

final sensorRepositoryProvider = Provider<SensorRepository>((ref) {
  return SensorRepository(ref.watch(apiClientProvider));
});
