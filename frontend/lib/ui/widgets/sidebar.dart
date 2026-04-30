import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import 'panel_card.dart';

class SidebarNav extends StatelessWidget {
  /// Route key of the page the sidebar is rendered on. Highlights the
  /// matching nav item. Accepted values: 'overview', 'telemetry', 'logs',
  /// 'settings'.
  final String active;
  const SidebarNav({super.key, this.active = 'overview'});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 168,
      decoration: const BoxDecoration(
        color: AppColors.sidebar,
        border: Border(
          right: BorderSide(color: AppColors.line, width: 1),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Brand
          Container(
            padding: const EdgeInsets.fromLTRB(16, 22, 16, 18),
            decoration: const BoxDecoration(
              border:
                  Border(bottom: BorderSide(color: AppColors.line, width: 1)),
            ),
            child: Row(
              children: [
                CustomPaint(size: const Size(18, 18), painter: _BrandMark()),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: const [
                    Text(
                      'AIRSIM',
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 3.2,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'GROUND CONTROL',
                      style: TextStyle(
                        color: AppColors.textMute,
                        fontSize: 7.5,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 1.8,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          // Section header
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text('OPERATIONS', style: AppText.label),
          ),
          // Nav
          _NavItem(
              icon: Icons.dashboard_outlined,
              label: 'OVERVIEW',
              active: active == 'overview',
              onTap: () {
                if (active != 'overview') context.go('/dashboard');
              }),
          _NavItem(
              icon: Icons.public_outlined,
              label: 'MAP',
              onTap: () => _comingSoon(context, 'MAP')),
          _NavItem(
              icon: Icons.tune,
              label: 'CONTROL',
              onTap: () => _comingSoon(context, 'CONTROL')),
          _NavItem(
              icon: Icons.memory_outlined,
              label: 'SYSTEMS',
              active: active == 'systems',
              onTap: () {
                if (active != 'systems') context.go('/systems');
              }),
          _NavItem(
              icon: Icons.timeline_outlined,
              label: 'TELEMETRY',
              active: active == 'telemetry',
              onTap: () {
                if (active != 'telemetry') context.go('/telemetry');
              }),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 22, 16, 8),
            child: Text('ADMIN', style: AppText.label),
          ),
          _NavItem(
              icon: Icons.article_outlined,
              label: 'LOGS',
              active: active == 'logs',
              onTap: () {
                if (active != 'logs') context.go('/logs');
              }),
          _NavItem(
              icon: Icons.settings_outlined,
              label: 'SETTINGS',
              active: active == 'settings',
              onTap: () {
                if (active != 'settings') context.go('/settings');
              }),
          const Spacer(),
          // Bottom system info
          Container(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
            decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: AppColors.line, width: 1)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                InlineStatus(text: 'NOMINAL', color: AppColors.ok),
                SizedBox(height: 10),
                _KV(k: 'CALLSIGN', v: 'ALPHA-SCOUT'),
                SizedBox(height: 4),
                _KV(k: 'SYS ID', v: 'AS-4712'),
                SizedBox(height: 4),
                _KV(k: 'BUILD', v: 'v2.4.1'),
                SizedBox(height: 8),
                Text('// FOUO',
                    style: TextStyle(
                      fontSize: 8.5,
                      letterSpacing: 1.4,
                      color: AppColors.textMute,
                      fontWeight: FontWeight.w500,
                    )),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _KV extends StatelessWidget {
  final String k;
  final String v;
  const _KV({required this.k, required this.v});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(k,
            style: const TextStyle(
              fontSize: 8.5,
              letterSpacing: 1.4,
              color: AppColors.textMute,
              fontWeight: FontWeight.w500,
            )),
        Text(v,
            style: AppText.dataSmall
                .copyWith(fontSize: 9.5, color: AppColors.textDim)),
      ],
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool active;
  final VoidCallback? onTap;
  const _NavItem({
    required this.icon,
    required this.label,
    this.active = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final fg = active ? AppColors.text : AppColors.textDim;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        hoverColor: AppColors.panel2.withOpacity(0.6),
        child: Container(
          decoration: BoxDecoration(
            color: active ? AppColors.panel2 : Colors.transparent,
            border: Border(
              left: BorderSide(
                color: active ? AppColors.accent : Colors.transparent,
                width: 2,
              ),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 14),
            child: Row(
              children: [
                Icon(icon, size: 14, color: fg),
                const SizedBox(width: 12),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 1.6,
                    fontWeight: FontWeight.w500,
                    color: fg,
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

void _comingSoon(BuildContext context, String section) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        backgroundColor: AppColors.panel,
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 2),
        shape: RoundedRectangleBorder(
          side: const BorderSide(color: AppColors.line, width: 1),
          borderRadius: BorderRadius.circular(2),
        ),
        content: Text(
          '$section  //  MODULE OFFLINE',
          style: const TextStyle(
            color: AppColors.accent,
            fontSize: 10.5,
            letterSpacing: 1.6,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
}

class _BrandMark extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // Minimal monochrome chevron mark
    final stroke = Paint()
      ..color = AppColors.text
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..strokeJoin = StrokeJoin.miter;
    final p = Path()
      ..moveTo(size.width * 0.10, size.height * 0.78)
      ..lineTo(size.width * 0.50, size.height * 0.18)
      ..lineTo(size.width * 0.90, size.height * 0.78);
    canvas.drawPath(p, stroke);
    final accent = Paint()
      ..color = AppColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    canvas.drawLine(
      Offset(size.width * 0.30, size.height * 0.92),
      Offset(size.width * 0.70, size.height * 0.92),
      accent,
    );
  }

  @override
  bool shouldRepaint(covariant _BrandMark oldDelegate) => false;
}
