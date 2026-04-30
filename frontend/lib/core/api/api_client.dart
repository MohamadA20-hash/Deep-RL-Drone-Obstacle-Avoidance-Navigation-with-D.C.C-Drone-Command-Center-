import 'package:dio/dio.dart';

import '../auth/auth_storage.dart';
import '../config/app_config.dart';

/// Configured Dio instance for talking to the Spring backend.
///
/// Responsibilities:
///   - inject `Authorization: Bearer <token>` from secure storage
///   - on a 401, attempt a single refresh via `/api/auth/refresh` and replay
///     the original request once
///   - surface backend `ApiResponse.message` strings as the DioException
///     message so UI layers get a readable error
class ApiClient {
  ApiClient(this._storage, {Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: AppConfig.apiBaseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 15),
              contentType: 'application/json',
              responseType: ResponseType.json,
            )) {
    _dio.interceptors.add(_AuthInterceptor(_storage, _dio, this));
  }

  final Dio _dio;
  final AuthStorage _storage;

  /// Called by AuthRepository after a successful refresh-token call so the
  /// interceptor stops being in "refreshing" state.
  void notifyRefreshed() => _refreshing = false;

  /// Set by the interceptor to coalesce concurrent refresh attempts.
  bool _refreshing = false;

  Dio get dio => _dio;
}

class _AuthInterceptor extends Interceptor {
  _AuthInterceptor(this._storage, this._dio, this._client);

  final AuthStorage _storage;
  final Dio _dio;
  final ApiClient _client;

  static const _authPaths = [
    '/api/auth/login',
    '/api/auth/register',
    '/api/auth/refresh'
  ];

  @override
  Future<void> onRequest(
      RequestOptions options, RequestInterceptorHandler handler) async {
    if (!_authPaths.any(options.path.contains)) {
      final token = await _storage.readAccessToken();
      if (token != null && token.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $token';
      }
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
      DioException err, ErrorInterceptorHandler handler) async {
    final status = err.response?.statusCode;
    final path = err.requestOptions.path;
    final isRefreshable = status == 401 &&
        !path.contains('/api/auth/login') &&
        !path.contains('/api/auth/refresh') &&
        err.requestOptions.extra['retried'] != true;

    if (isRefreshable) {
      final refresh = await _storage.readRefreshToken();
      if (refresh != null && refresh.isNotEmpty && !_client._refreshing) {
        _client._refreshing = true;
        try {
          final r = await _dio
              .post('/api/auth/refresh', data: {'refreshToken': refresh});
          final data =
              (r.data is Map ? r.data['data'] : null) as Map<String, dynamic>?;
          if (data != null) {
            await _storage.saveTokens(
              access: data['token'] as String,
              refresh: data['refreshToken'] as String,
            );
            // replay
            final req = err.requestOptions;
            req.extra['retried'] = true;
            req.headers['Authorization'] = 'Bearer ${data['token']}';
            final cloned = await _dio.fetch(req);
            return handler.resolve(cloned);
          }
        } catch (_) {
          await _storage.clear();
        } finally {
          _client._refreshing = false;
        }
      } else {
        await _storage.clear();
      }
    }

    // Surface a friendlier message from the backend's ApiResponse envelope.
    // We keep the original response intact so callers can still read
    // `data['errors']`, `statusCode`, etc.
    final body = err.response?.data;
    if (body is Map && body['message'] is String) {
      return handler.next(err.copyWith(
        error: body['message'],
        message: body['message'] as String,
      ));
    }
    handler.next(err);
  }
}
