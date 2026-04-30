import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Persists JWT + refresh token across launches.
///
/// Uses `flutter_secure_storage` on real platforms (Keychain / Keystore /
/// libsecret / DPAPI) and falls back to `shared_preferences` on web because
/// secure storage on web is just localStorage anyway and is occasionally
/// flaky in dev.
class AuthStorage {
  static const _kAccess = 'auth.access';
  static const _kRefresh = 'auth.refresh';

  final FlutterSecureStorage _secure = const FlutterSecureStorage();

  Future<void> saveTokens({
    required String access,
    required String refresh,
  }) async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kAccess, access);
      await prefs.setString(_kRefresh, refresh);
      return;
    }
    await _secure.write(key: _kAccess, value: access);
    await _secure.write(key: _kRefresh, value: refresh);
  }

  Future<String?> readAccessToken() async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_kAccess);
    }
    return _secure.read(key: _kAccess);
  }

  Future<String?> readRefreshToken() async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_kRefresh);
    }
    return _secure.read(key: _kRefresh);
  }

  Future<void> clear() async {
    if (kIsWeb) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_kAccess);
      await prefs.remove(_kRefresh);
      return;
    }
    await _secure.delete(key: _kAccess);
    await _secure.delete(key: _kRefresh);
  }
}
