import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/login_page.dart';
import '../../features/auth/register_page.dart';
import '../../features/settings/settings_page.dart';
import '../../features/system/logs_page.dart';
import '../../features/system/systems_page.dart';
import '../../features/system/telemetry_page.dart';
import '../../ui/dashboard_page.dart';
import '../auth/auth_controller.dart';

/// Single-source-of-truth router. The redirect callback consults the auth
/// controller so:
///   - unauthenticated users are bounced to /login (except for /register)
///   - authenticated users on /login or /register are bounced to /dashboard
final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authControllerProvider);

  return GoRouter(
    initialLocation: '/dashboard',
    refreshListenable: _RiverpodAuthListenable(ref),
    redirect: (context, state) {
      if (auth.initializing) return null; // splash will render
      final loggedIn = auth.isAuthenticated;
      final loc = state.matchedLocation;
      final atAuthPage = loc == '/login' || loc == '/register';

      if (!loggedIn && !atAuthPage) return '/login';
      if (loggedIn && atAuthPage) return '/dashboard';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginPage()),
      GoRoute(path: '/register', builder: (_, __) => const RegisterPage()),
      GoRoute(path: '/dashboard', builder: (_, __) => const DashboardPage()),
      GoRoute(path: '/settings', builder: (_, __) => const SettingsPage()),
      GoRoute(path: '/logs', builder: (_, __) => const LogsPage()),
      GoRoute(path: '/telemetry', builder: (_, __) => const TelemetryPage()),
      GoRoute(path: '/systems', builder: (_, __) => const SystemsPage()),
    ],
    errorBuilder: (context, state) => Scaffold(
      backgroundColor: const Color(0xFF06080B),
      body: Center(
        child: Text(
          'NAV ERROR  ${state.error?.message ?? ''}',
          style: const TextStyle(
              color: Color(0xFFC75450), letterSpacing: 2, fontFamily: 'Inter'),
        ),
      ),
    ),
  );
});

/// Bridges Riverpod auth state changes to GoRouter's `refreshListenable`.
class _RiverpodAuthListenable extends ChangeNotifier {
  _RiverpodAuthListenable(Ref ref) {
    ref.listen<AuthState>(authControllerProvider, (_, __) => notifyListeners());
  }
}
