/// Strongly-typed mirror of the backend auth DTOs.
///
/// Backend wraps everything in `ApiResponse<T> { success, message, data, ... }`,
/// so the repository unwraps `data` before constructing these.
class AuthTokens {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresInMs;
  final AuthUser user;

  const AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.expiresInMs,
    required this.user,
  });

  factory AuthTokens.fromJson(Map<String, dynamic> json) => AuthTokens(
        accessToken: json['token'] as String,
        refreshToken: json['refreshToken'] as String,
        tokenType: (json['tokenType'] as String?) ?? 'Bearer',
        expiresInMs: (json['expiresIn'] as num?)?.toInt() ?? 0,
        user: AuthUser(
          id: json['userId']?.toString(),
          username: json['username'] as String? ?? '',
          email: json['email'] as String? ?? '',
        ),
      );
}

class AuthUser {
  final String? id;
  final String username;
  final String email;
  final bool enabled;

  const AuthUser({
    this.id,
    required this.username,
    required this.email,
    this.enabled = true,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: json['id']?.toString(),
        username: json['username'] as String? ?? '',
        email: json['email'] as String? ?? '',
        enabled: json['enabled'] as bool? ?? true,
      );
}
