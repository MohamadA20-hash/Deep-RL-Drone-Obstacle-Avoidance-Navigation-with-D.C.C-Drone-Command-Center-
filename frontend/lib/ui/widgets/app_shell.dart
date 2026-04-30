import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/state/fleet_providers.dart';
import '../theme.dart';
import 'sidebar.dart';
import 'topbar.dart';
import 'footer.dart';

/// Shared chrome (sidebar + topbar + footer + page title strip) used by all
/// post-dashboard pages so they look like first-class views, not popups.
///
/// Mirrors `DashboardPage`'s outer 1480x830 fitted container so the entire
/// app renders identically across resolutions.
class AppShell extends ConsumerWidget {
  final String activeRoute; // overview | telemetry | logs | settings
  final String title;
  final String subtitle;
  final Widget child;
  final Widget? trailing;
  const AppShell({
    super.key,
    required this.activeRoute,
    required this.title,
    required this.subtitle,
    required this.child,
    this.trailing,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bridgeAsync = ref.watch(bridgeStatusProvider);
    final unreachable = bridgeAsync.asData?.value.status == 'unreachable' ||
        bridgeAsync.hasError;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: FittedBox(
          fit: BoxFit.contain,
          child: Container(
            width: 1480,
            height: 830,
            decoration: BoxDecoration(
              color: AppColors.bg,
              borderRadius: BorderRadius.circular(2),
            ),
            clipBehavior: Clip.antiAlias,
            child: Row(
              children: [
                SidebarNav(active: activeRoute),
                Expanded(
                  child: Container(
                    color: AppColors.main,
                    padding: const EdgeInsets.all(10),
                    child: Column(
                      children: [
                        const Topbar(),
                        if (unreachable) ...[
                          const SizedBox(height: 8),
                          const _ConnectionBanner(),
                        ],
                        const SizedBox(height: 10),
                        _PageHeader(
                            title: title,
                            subtitle: subtitle,
                            trailing: trailing),
                        const SizedBox(height: 10),
                        Expanded(child: child),
                        const SizedBox(height: 8),
                        const FooterBar(),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ConnectionBanner extends StatelessWidget {
  const _ConnectionBanner();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF2A1418),
        border: Border.all(color: AppColors.alert, width: 1),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, color: AppColors.alert, size: 14),
          const SizedBox(width: 10),
          const Text(
            'BACKEND UNREACHABLE  //  Spring API not responding. '
            'Telemetry, logs and command rails are paused until the connection recovers.',
            style: TextStyle(
              color: AppColors.alert,
              fontSize: 10.5,
              letterSpacing: 1.4,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _PageHeader extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget? trailing;
  const _PageHeader(
      {required this.title, required this.subtitle, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.panel,
        border: Border.all(color: AppColors.line, width: 1),
      ),
      child: Row(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(title.toUpperCase(),
                  style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 2.4,
                  )),
              const SizedBox(height: 3),
              Text(subtitle,
                  style: const TextStyle(
                    color: AppColors.textMute,
                    fontSize: 9,
                    letterSpacing: 1.4,
                  )),
            ],
          ),
          const Spacer(),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
