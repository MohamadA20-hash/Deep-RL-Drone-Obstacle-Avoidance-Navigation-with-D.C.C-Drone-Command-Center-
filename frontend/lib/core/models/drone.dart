/// Strongly-typed mirror of backend `DroneDTO`.
class Drone {
  final String id;
  final String? serialNumber;
  final String name;
  final String? modelType;
  final String? firmwareVersion;
  final String? connectionStatus;
  final String? flightStatus;
  final double batteryLevel;
  final double latitude;
  final double longitude;
  final double altitude;
  final String? autonomyLevel;
  final String? navigationMode;
  final bool failsafeEnabled;
  final bool obstacleDetected;
  final DateTime? lastHeartbeat;
  final DateTime? registeredAt;
  final double? homeLatitude;
  final double? homeLongitude;
  final double? homeAltitude;
  final double? positionNedX;
  final double? positionNedY;
  final double? positionNedZ;
  final double? goalNedX;
  final double? goalNedY;
  final double? navigationEfficiency;
  final int? totalReplanCount;
  final double? distanceToGoal;
  final String? altitudeMode;

  const Drone({
    required this.id,
    required this.name,
    this.serialNumber,
    this.modelType,
    this.firmwareVersion,
    this.connectionStatus,
    this.flightStatus,
    this.batteryLevel = 0,
    this.latitude = 0,
    this.longitude = 0,
    this.altitude = 0,
    this.autonomyLevel,
    this.navigationMode,
    this.failsafeEnabled = false,
    this.obstacleDetected = false,
    this.lastHeartbeat,
    this.registeredAt,
    this.homeLatitude,
    this.homeLongitude,
    this.homeAltitude,
    this.positionNedX,
    this.positionNedY,
    this.positionNedZ,
    this.goalNedX,
    this.goalNedY,
    this.navigationEfficiency,
    this.totalReplanCount,
    this.distanceToGoal,
    this.altitudeMode,
  });

  factory Drone.fromJson(Map<String, dynamic> j) => Drone(
        id: j['id'].toString(),
        serialNumber: j['serialNumber'] as String?,
        name: (j['name'] as String?) ?? 'UNNAMED',
        modelType: j['modelType'] as String?,
        firmwareVersion: j['firmwareVersion'] as String?,
        connectionStatus: j['connectionStatus']?.toString(),
        flightStatus: j['flightStatus']?.toString(),
        batteryLevel: _d(j['batteryLevel']),
        latitude: _d(j['latitude']),
        longitude: _d(j['longitude']),
        altitude: _d(j['altitude']),
        autonomyLevel: j['autonomyLevel']?.toString(),
        navigationMode: j['navigationMode']?.toString(),
        failsafeEnabled: j['failsafeEnabled'] == true,
        obstacleDetected: j['obstacleDetected'] == true,
        lastHeartbeat: _ts(j['lastHeartbeat']),
        registeredAt: _ts(j['registeredAt']),
        homeLatitude: _dn(j['homeLatitude']),
        homeLongitude: _dn(j['homeLongitude']),
        homeAltitude: _dn(j['homeAltitude']),
        positionNedX: _dn(j['positionNedX']),
        positionNedY: _dn(j['positionNedY']),
        positionNedZ: _dn(j['positionNedZ']),
        goalNedX: _dn(j['goalNedX']),
        goalNedY: _dn(j['goalNedY']),
        navigationEfficiency: _dn(j['navigationEfficiency']),
        totalReplanCount: (j['totalReplanCount'] as num?)?.toInt(),
        distanceToGoal: _dn(j['distanceToGoal']),
        altitudeMode: j['altitudeMode'] as String?,
      );

  static double _d(dynamic v) => (v as num?)?.toDouble() ?? 0;
  static double? _dn(dynamic v) => (v as num?)?.toDouble();
  static DateTime? _ts(dynamic v) =>
      v == null ? null : DateTime.tryParse(v.toString());
}
