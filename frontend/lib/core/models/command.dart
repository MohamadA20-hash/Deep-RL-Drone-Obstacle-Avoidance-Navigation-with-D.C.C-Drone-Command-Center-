/// Mirror of backend `CommandType` enum.
enum DroneCommandType {
  takeoff('TAKEOFF'),
  land('LAND'),
  move('MOVE'),
  setMode('SET_MODE'),
  emergencyStop('EMERGENCY_STOP'),
  setGoal('SET_GOAL'),
  startAutonomousNav('START_AUTONOMOUS_NAV'),
  stopAutonomousNav('STOP_AUTONOMOUS_NAV'),
  forceReplan('FORCE_REPLAN'),
  pauseNav('PAUSE_NAV'),
  resumeNav('RESUME_NAV'),
  setPlannerConfig('SET_PLANNER_CONFIG');

  final String wire;
  const DroneCommandType(this.wire);
}

class DroneCommand {
  final String? id;
  final String droneId;
  final DroneCommandType type;

  /// JSON-encoded string passed straight through to the backend.
  final String? parameters;
  final String? status;
  final DateTime? createdAt;

  const DroneCommand({
    this.id,
    required this.droneId,
    required this.type,
    this.parameters,
    this.status,
    this.createdAt,
  });

  Map<String, dynamic> toRequest() => {
        'droneId': droneId,
        'commandType': type.wire,
        if (parameters != null) 'parameters': parameters,
      };

  factory DroneCommand.fromJson(Map<String, dynamic> j) => DroneCommand(
        id: j['id']?.toString(),
        droneId: j['droneId']?.toString() ?? '',
        type: DroneCommandType.values.firstWhere(
          (t) => t.wire == (j['commandType']?.toString()),
          orElse: () => DroneCommandType.move,
        ),
        parameters: j['parameters']?.toString(),
        status: j['status']?.toString(),
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'].toString()),
      );
}
