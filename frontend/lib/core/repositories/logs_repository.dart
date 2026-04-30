import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../auth/auth_controller.dart';

class LogEntry {
  final String ts;
  final String level;
  final String thread;
  final String logger;
  final String message;
  final String? stack;
  LogEntry({
    required this.ts,
    required this.level,
    required this.thread,
    required this.logger,
    required this.message,
    this.stack,
  });

  factory LogEntry.fromJson(Map<String, dynamic> j) => LogEntry(
        ts: j['ts'] as String? ?? '',
        level: j['level'] as String? ?? 'INFO',
        thread: j['thread'] as String? ?? '',
        logger: j['logger'] as String? ?? '',
        message: j['message'] as String? ?? '',
        stack: j['stack'] as String?,
      );
}

class LogsResult {
  final List<LogEntry> entries;
  final bool exists;
  final String path;
  LogsResult({required this.entries, required this.exists, required this.path});
}

class LogsRepository {
  LogsRepository(this._client);
  final ApiClient _client;

  Future<LogsResult> recent({int limit = 200, String? level, String? q}) async {
    try {
      final r = await _client.dio.get('/api/logs/recent', queryParameters: {
        'limit': limit,
        if (level != null && level.isNotEmpty && level != 'ALL') 'level': level,
        if (q != null && q.isNotEmpty) 'q': q,
      });
      final body = r.data is Map ? (r.data['data'] ?? r.data) : null;
      if (body is Map) {
        final list = (body['entries'] as List?) ?? const [];
        return LogsResult(
          entries: list
              .whereType<Map>()
              .map((e) => LogEntry.fromJson(Map<String, dynamic>.from(e)))
              .toList(),
          exists: body['exists'] == true,
          path: (body['path'] as String?) ?? '',
        );
      }
    } on DioException {
      // fall through
    }
    return LogsResult(entries: const [], exists: false, path: '');
  }
}

final logsRepositoryProvider = Provider<LogsRepository>((ref) {
  return LogsRepository(ref.watch(apiClientProvider));
});
