import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';

/// Compile / runtime config for the AIRSIM frontend.
///
/// Backend base URL resolution order:
///   1. `--dart-define=API_BASE_URL=...` (preferred for builds / CI)
///   2. Per-platform sensible default (Android emulator vs. desktop / web)
class AppConfig {
  AppConfig._();

  /// REST base URL (no trailing slash).
  static String get apiBaseUrl {
    const fromEnv = String.fromEnvironment('API_BASE_URL');
    if (fromEnv.isNotEmpty) return fromEnv;
    return _defaultHttpBase();
  }

  /// WebSocket base URL (no trailing slash).
  static String get wsBaseUrl {
    const fromEnv = String.fromEnvironment('WS_BASE_URL');
    if (fromEnv.isNotEmpty) return fromEnv;
    final http = _defaultHttpBase();
    return http.replaceFirst(RegExp(r'^http'), 'ws');
  }

  /// Telemetry stream endpoint.
  static String get telemetryWsUrl => '$wsBaseUrl/ws/telemetry';

  static String _defaultHttpBase() {
    // On the web the browser talks to the same host that served the app;
    // for `flutter run -d chrome` against a local backend that's localhost.
    if (kIsWeb) return 'http://localhost:8080';
    try {
      if (Platform.isAndroid) return 'http://10.0.2.2:8080';
    } catch (_) {/* Platform unavailable on web — already handled above */}
    return 'http://localhost:8080';
  }
}
