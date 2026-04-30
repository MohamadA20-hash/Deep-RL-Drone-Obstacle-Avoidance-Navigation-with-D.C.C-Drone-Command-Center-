import 'package:dio/dio.dart';

import '../api/api_client.dart';
import 'auth_models.dart';
import 'auth_storage.dart';

/// Thin wrapper over `/api/auth/*` endpoints.
class AuthRepository {
  AuthRepository(this._client, this._storage);

  final ApiClient _client;
  final AuthStorage _storage;

  Future<AuthTokens> login({
    required String username,
    required String password,
  }) async {
    final r = await _client.dio.post('/api/auth/login',
        data: {'username': username, 'password': password});
    final tokens = AuthTokens.fromJson(_unwrap(r));
    await _storage.saveTokens(
      access: tokens.accessToken,
      refresh: tokens.refreshToken,
    );
    return tokens;
  }

  Future<AuthUser> register({
    required String username,
    required String password,
    required String email,
  }) async {
    final r = await _client.dio.post('/api/auth/register', data: {
      'username': username,
      'password': password,
      'email': email,
    });
    return AuthUser.fromJson(_unwrap(r));
  }

  /// Returns the current user using the stored access token, or `null` if no
  /// token is stored or the token is invalid.
  Future<AuthUser?> me() async {
    final token = await _storage.readAccessToken();
    if (token == null || token.isEmpty) return null;
    try {
      final r = await _client.dio.get('/api/auth/me');
      return AuthUser.fromJson(_unwrap(r));
    } on DioException {
      return null;
    }
  }

  Future<void> logout() async {
    final refresh = await _storage.readRefreshToken();
    try {
      if (refresh != null && refresh.isNotEmpty) {
        await _client.dio
            .post('/api/auth/logout', data: {'refreshToken': refresh});
      }
    } on DioException {
      // ignore — we still want to wipe local tokens
    } finally {
      await _storage.clear();
    }
  }

  Map<String, dynamic> _unwrap(Response r) {
    final body = r.data;
    if (body is Map && body['data'] is Map) {
      return Map<String, dynamic>.from(body['data'] as Map);
    }
    if (body is Map) return Map<String, dynamic>.from(body);
    throw DioException(
      requestOptions: r.requestOptions,
      response: r,
      message: 'Unexpected response shape',
    );
  }
}
