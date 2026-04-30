import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../auth/auth_controller.dart';
import '../models/command.dart';

/// REST repository for `/api/commands`.
class CommandRepository {
  CommandRepository(this._client);
  final ApiClient _client;

  /// Send a command. Returns the persisted DTO on success, throws DioException
  /// on validation / authorization failure.
  Future<DroneCommand> send(DroneCommand command) async {
    final r =
        await _client.dio.post('/api/commands', data: command.toRequest());
    final d = _data(r);
    if (d is Map) {
      return DroneCommand.fromJson(Map<String, dynamic>.from(d));
    }
    throw DioException(
      requestOptions: r.requestOptions,
      response: r,
      message: 'Unexpected command response shape',
    );
  }

  static dynamic _data(Response r) {
    final body = r.data;
    if (body is Map && body.containsKey('data')) return body['data'];
    return body;
  }
}

final commandRepositoryProvider = Provider<CommandRepository>((ref) {
  return CommandRepository(ref.watch(apiClientProvider));
});
