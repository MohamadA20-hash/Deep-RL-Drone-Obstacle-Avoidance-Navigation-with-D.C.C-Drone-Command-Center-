/// Mirror of backend `AirSimBridgeManager.getStatusMap()`.
///
/// Backend `status` values observed: `stopped`, `starting`, `connecting`,
/// `running`, `restarting`, `error`. We treat anything that is not actively
/// streaming telemetry as not-online; the UI surface boils this down further
/// via [BridgeUiState].
class BridgeStatus {
  final String status;
  final String? message;
  final DateTime? since;
  final int telemetryCount;
  final bool processAlive;
  final int? pid;

  const BridgeStatus({
    required this.status,
    required this.processAlive,
    this.message,
    this.since,
    this.telemetryCount = 0,
    this.pid,
  });

  /// Sentinel used while the very first poll is still in-flight.
  factory BridgeStatus.unknown() => const BridgeStatus(
        status: 'unknown',
        processAlive: false,
      );

  factory BridgeStatus.fromJson(Map<String, dynamic> j) => BridgeStatus(
        status: (j['status'] as String?) ?? 'unknown',
        message: j['message'] as String?,
        since: j['since'] == null
            ? null
            : DateTime.tryParse(j['since'].toString()),
        telemetryCount: (j['telemetryCount'] as num?)?.toInt() ?? 0,
        processAlive: j['processAlive'] == true,
        pid: (j['pid'] as num?)?.toInt(),
      );
}

/// Tri-state used by the dashboard footer / status pills.
enum BridgeUiState {
  /// No status yet, or backend itself is unreachable.
  unknown,

  /// Bridge process is alive AND has been seen streaming telemetry recently.
  online,

  /// Bridge process is alive but is still searching / connecting / no
  /// telemetry yet — display as a flashing "SEARCHING" indicator.
  searching,

  /// Bridge process is not running (stopped / error).
  offline,
}
