/// Strongly-typed mirror of backend `TelemetryDTO`.
class Telemetry {
  final String? id;
  final DateTime? timestamp;
  final double latitude;
  final double longitude;
  final double altitude;
  final double velocityX;
  final double velocityY;
  final double velocityZ;
  final double yaw;
  final double pitch;
  final double roll;
  final double batteryLevel;
  final double obstacleDistance;
  final String? droneId;
  final String? droneName;

  // NavRL
  final double? positionNedX;
  final double? positionNedY;
  final double? positionNedZ;
  final String? altitudeMode;
  final int? stuckReplanCount;
  final int? proactiveReplanCount;
  final double? navigationEfficiency;
  final double? pathLength;
  final double? optimalDistance;
  final double? distanceToGoal;
  final int? mappedObstacleCells;
  final double? closestObstacleDistance;
  final bool? bestEffortActive;
  final int? collisionCount;
  final int? currentPathWaypointCount;
  final double? navrlSpeed;

  // Transient: lidar scan as compact JSON string from bridge.
  final String? lidarScan;

  const Telemetry({
    this.id,
    this.timestamp,
    this.latitude = 0,
    this.longitude = 0,
    this.altitude = 0,
    this.velocityX = 0,
    this.velocityY = 0,
    this.velocityZ = 0,
    this.yaw = 0,
    this.pitch = 0,
    this.roll = 0,
    this.batteryLevel = 0,
    this.obstacleDistance = 0,
    this.droneId,
    this.droneName,
    this.positionNedX,
    this.positionNedY,
    this.positionNedZ,
    this.altitudeMode,
    this.stuckReplanCount,
    this.proactiveReplanCount,
    this.navigationEfficiency,
    this.pathLength,
    this.optimalDistance,
    this.distanceToGoal,
    this.mappedObstacleCells,
    this.closestObstacleDistance,
    this.bestEffortActive,
    this.collisionCount,
    this.currentPathWaypointCount,
    this.navrlSpeed,
    this.lidarScan,
  });

  /// Computed ground speed in m/s from velocity components.
  double get groundSpeed {
    final vx = velocityX, vy = velocityY;
    return (vx * vx + vy * vy).abs() == 0 ? 0 : _sqrt(vx * vx + vy * vy);
  }

  /// Heading in degrees (0..360) derived from yaw (radians).
  double get headingDeg {
    final h = (yaw * 180 / 3.141592653589793) % 360;
    return h < 0 ? h + 360 : h;
  }

  factory Telemetry.fromJson(Map<String, dynamic> j) => Telemetry(
        id: j['id']?.toString(),
        timestamp: j['timestamp'] == null
            ? null
            : DateTime.tryParse(j['timestamp'].toString()),
        latitude: _d(j['latitude']),
        longitude: _d(j['longitude']),
        altitude: _d(j['altitude']),
        velocityX: _d(j['velocityX']),
        velocityY: _d(j['velocityY']),
        velocityZ: _d(j['velocityZ']),
        yaw: _d(j['yaw']),
        pitch: _d(j['pitch']),
        roll: _d(j['roll']),
        batteryLevel: _d(j['batteryLevel']),
        obstacleDistance: _d(j['obstacleDistance']),
        droneId: j['droneId']?.toString(),
        droneName: j['droneName']?.toString(),
        positionNedX: _dn(j['positionNedX']),
        positionNedY: _dn(j['positionNedY']),
        positionNedZ: _dn(j['positionNedZ']),
        altitudeMode: j['altitudeMode'] as String?,
        stuckReplanCount: (j['stuckReplanCount'] as num?)?.toInt(),
        proactiveReplanCount: (j['proactiveReplanCount'] as num?)?.toInt(),
        navigationEfficiency: _dn(j['navigationEfficiency']),
        pathLength: _dn(j['pathLength']),
        optimalDistance: _dn(j['optimalDistance']),
        distanceToGoal: _dn(j['distanceToGoal']),
        mappedObstacleCells: (j['mappedObstacleCells'] as num?)?.toInt(),
        closestObstacleDistance: _dn(j['closestObstacleDistance']),
        bestEffortActive: j['bestEffortActive'] as bool?,
        collisionCount: (j['collisionCount'] as num?)?.toInt(),
        currentPathWaypointCount:
            (j['currentPathWaypointCount'] as num?)?.toInt(),
        navrlSpeed: _dn(j['navrlSpeed']),
        lidarScan: j['lidarScan'] as String?,
      );

  static double _d(dynamic v) => (v as num?)?.toDouble() ?? 0;
  static double? _dn(dynamic v) => (v as num?)?.toDouble();
  static double _sqrt(double v) {
    // Avoid importing dart:math at top-level for a single use.
    var x = v, y = 1.0;
    for (var i = 0; i < 16; i++) {
      x = (x + y) / 2;
      y = v / x;
    }
    return x;
  }
}
