import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/auth/auth_controller.dart';
import 'core/notifications/notification_center.dart';
import 'core/router/app_router.dart';
import 'ui/theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
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
        home: const _BootSplash(),
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

class _BootSplash extends StatelessWidget {
  const _BootSplash();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: const [
            SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(
                strokeWidth: 1.4,
                valueColor: AlwaysStoppedAnimation(AppColors.accent),
              ),
            ),
            SizedBox(height: 18),
            Text(
              'AIRSIM  //  INITIALIZING',
              style: TextStyle(
                color: AppColors.textDim,
                fontSize: 10,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
