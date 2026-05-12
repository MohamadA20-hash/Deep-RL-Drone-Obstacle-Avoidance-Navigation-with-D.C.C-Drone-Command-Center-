import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/auth/auth_controller.dart';
import 'core/notifications/notification_center.dart';
import 'core/router/app_router.dart';
import 'ui/theme.dart';
import 'ui/widgets/splash_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Force landscape orientation on mobile devices so the dashboard layout
  // (designed for wide aspect ratios) renders correctly on phones/tablets.
  await SystemChrome.setPreferredOrientations(<DeviceOrientation>[
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
  ]);
  // Hide system bars on mobile to give the dashboard the full screen.
  // Users can swipe from the edge to temporarily reveal them.
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: Color(0xFF06080B),
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );
  runApp(const ProviderScope(child: DroneCommandCenterApp()));
}

class DroneCommandCenterApp extends ConsumerWidget {
  const DroneCommandCenterApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);

    // Block the router during the initial /api/auth/me bootstrap so we don't
    // briefly flash the login screen for users with valid stored tokens.
    if (auth.initializing) {
      return MaterialApp(
        title: 'AIRSIM Ground Control',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark,
        home: const SplashScreen(),
      );
    }

    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'AIRSIM Ground Control',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      routerConfig: router,
      builder: (context, child) =>
          NotificationOverlay(child: child ?? const SizedBox.shrink()),
    );
  }
}
