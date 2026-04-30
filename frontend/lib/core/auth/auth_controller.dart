import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import 'auth_models.dart';
import 'auth_repository.dart';
import 'auth_storage.dart';

final authStorageProvider = Provider<AuthStorage>((_) => AuthStorage());

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(ref.watch(authStorageProvider));
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
    ref.watch(apiClientProvider),
    ref.watch(authStorageProvider),
  );
});

/// A normalized error surfaced to the UI. Carries the HTTP status code and
/// any per-field validation errors returned by the backend so the auth
/// pages can render them properly.
class AuthError {
  final String message;
  final int? statusCode;
  final List<String> details;

  const AuthError({
    required this.message,
    this.statusCode,
    this.details = const [],
  });

  @override
  String toString() => 'AuthError($statusCode, $message)';
}

class AuthState {
  final AuthUser? user;
  final bool initializing;
  final AuthError? error;

  const AuthState({
    this.user,
    this.initializing = false,
    this.error,
  });

  bool get isAuthenticated => user != null;

  AuthState copyWith({AuthUser? user, bool? initializing, AuthError? error}) {
    return AuthState(
      user: user ?? this.user,
      initializing: initializing ?? this.initializing,
      error: error,
    );
  }
}

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._repo) : super(const AuthState(initializing: true)) {
    _bootstrap();
  }

  final AuthRepository _repo;

  Future<void> _bootstrap() async {
    final user = await _repo.me();
    state = AuthState(user: user, initializing: false);
  }

  Future<bool> login(String username, String password) async {
    state = state.copyWith(error: null);
    try {
      final tokens = await _repo.login(username: username, password: password);
      state = AuthState(user: tokens.user);
      return true;
    } on DioException catch (e) {
      state = state.copyWith(error: _mapDioError(e, 'Login failed'));
      return false;
    } catch (e) {
      state = state.copyWith(error: AuthError(message: e.toString()));
      return false;
    }
  }

  Future<bool> register({
    required String username,
    required String password,
    required String email,
  }) async {
    state = state.copyWith(error: null);
    try {
      await _repo.register(
          username: username, password: password, email: email);
      // Auto-login after register so the user lands straight in the app.
      return login(username, password);
    } on DioException catch (e) {
      state = state.copyWith(error: _mapDioError(e, 'Registration failed'));
      return false;
    } catch (e) {
      state = state.copyWith(error: AuthError(message: e.toString()));
      return false;
    }
  }

  Future<void> logout() async {
    await _repo.logout();
    state = const AuthState();
  }

  void clearError() {
    if (state.error != null) state = state.copyWith(error: null);
  }

  AuthError _mapDioError(DioException e, String fallback) {
    final status = e.response?.statusCode;
    final body = e.response?.data;
    String message = e.message ?? fallback;
    final details = <String>[];
    if (body is Map) {
      if (body['message'] is String) message = body['message'] as String;
      final errs = body['errors'];
      if (errs is List) {
        for (final v in errs) {
          if (v != null) details.add(v.toString());
        }
      }
    }
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.connectionError) {
      message = 'Cannot reach server at ${e.requestOptions.baseUrl}';
    }
    return AuthError(message: message, statusCode: status, details: details);
  }
}

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref.watch(authRepositoryProvider));
});
