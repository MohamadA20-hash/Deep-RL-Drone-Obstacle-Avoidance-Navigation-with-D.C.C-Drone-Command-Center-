import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/auth/auth_controller.dart';
import '../../core/config/app_config.dart';
import '../../core/models/bridge_status.dart';
import '../../core/notifications/notification_center.dart';
import '../../core/repositories/bridge_repository.dart';
import '../../core/state/fleet_providers.dart';
import '../../ui/theme.dart';
import '../../ui/widgets/app_shell.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  static const _kReducedMotion = 'pref.reducedMotion';
  static const _kCompactMode = 'pref.compact';
  static const _kAutoCenterMap = 'pref.autoCenterMap';

  bool _reducedMotion = false;
  bool _compact = false;
  bool _autoCenterMap = true;
  bool _bridgeBusy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final p = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _reducedMotion = p.getBool(_kReducedMotion) ?? false;
      _compact = p.getBool(_kCompactMode) ?? false;
      _autoCenterMap = p.getBool(_kAutoCenterMap) ?? true;
    });
  }

  Future<void> _save(String key, bool value) async {
    final p = await SharedPreferences.getInstance();
    await p.setBool(key, value);
  }

  Color _bridgeColor(BridgeUiState s) {
    switch (s) {
      case BridgeUiState.online:
        return AppColors.ok;
      case BridgeUiState.searching:
        return AppColors.warn;
      case BridgeUiState.offline:
        return AppColors.alert;
      case BridgeUiState.unknown:
        return AppColors.textDim;
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final bridge = ref.watch(bridgeStatusProvider).asData?.value;
    final bridgeUi = ref.watch(bridgeUiStateProvider);
    final streaming = ref.watch(airsimStreamingProvider).asData?.value ?? false;

    return AppShell(
      activeRoute: 'settings',
      title: 'Settings',
      subtitle: 'Operator preferences // pipeline diagnostics',
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _Section(
              title: 'PIPELINE',
              children: [
                _KvRow(
                    k: 'Backend',
                    v: AppConfig.apiBaseUrl,
                    valueColor: AppColors.text),
                _KvRow(k: 'Telemetry WS', v: AppConfig.telemetryWsUrl),
                _KvRow(
                  k: 'Bridge',
                  v: '${bridgeUi.name.toUpperCase()}'
                      '${bridge != null && bridge.processAlive ? '  //  PID ${bridge.pid ?? '-'}' : ''}',
                  valueColor: _bridgeColor(bridgeUi),
                ),
                _KvRow(
                    k: 'AirSim stream',
                    v: streaming ? 'LIVE' : 'OFFLINE',
                    valueColor: streaming ? AppColors.ok : AppColors.alert),
              ],
              trailing: Wrap(
                spacing: 8,
                children: [
                  _Btn(
                    label: 'START BRIDGE',
                    icon: Icons.play_arrow,
                    onPressed: _bridgeBusy
                        ? null
                        : () => _bridgeAction(
                              'start',
                              () => ref
                                  .read(bridgeRepositoryProvider)
                                  .startBridge(),
                            ),
                  ),
                  _Btn(
                    label: 'RESTART BRIDGE',
                    icon: Icons.refresh,
                    onPressed: _bridgeBusy
                        ? null
                        : () => _bridgeAction(
                              'restart',
                              () => ref
                                  .read(bridgeRepositoryProvider)
                                  .restartBridge(),
                            ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            _Section(
              title: 'DISPLAY',
              children: [
                _SwitchRow(
                  label: 'Reduced motion',
                  description:
                      'Disable non-essential animations (helpful on older GPUs).',
                  value: _reducedMotion,
                  onChanged: (v) {
                    setState(() => _reducedMotion = v);
                    _save(_kReducedMotion, v);
                  },
                ),
                _SwitchRow(
                  label: 'Compact panels',
                  description: 'Reserve space for more telemetry rows.',
                  value: _compact,
                  onChanged: (v) {
                    setState(() => _compact = v);
                    _save(_kCompactMode, v);
                  },
                ),
                _SwitchRow(
                  label: 'Auto-center map on drone',
                  description:
                      'Map view follows the selected drone\'s NED position.',
                  value: _autoCenterMap,
                  onChanged: (v) {
                    setState(() => _autoCenterMap = v);
                    _save(_kAutoCenterMap, v);
                  },
                ),
              ],
            ),
            const SizedBox(height: 10),
            _Section(
              title: 'OPERATOR',
              children: [
                _KvRow(k: 'Username', v: auth.user?.username ?? '—'),
                _KvRow(k: 'Email', v: auth.user?.email ?? '—'),
                _KvRow(
                    k: 'Auth state',
                    v: auth.isAuthenticated ? 'AUTHENTICATED' : 'GUEST',
                    valueColor:
                        auth.isAuthenticated ? AppColors.ok : AppColors.alert),
              ],
              trailing: _Btn(
                label: 'SIGN OUT',
                icon: Icons.logout,
                danger: true,
                onPressed: () async {
                  await ref.read(authControllerProvider.notifier).logout();
                  if (mounted && context.mounted) {
                    Navigator.of(context).maybePop();
                  }
                },
              ),
            ),
            const SizedBox(height: 10),
            _Section(
              title: 'ABOUT',
              children: const [
                _KvRow(k: 'Build', v: 'AIRSIM Ground Control v2.4.1'),
                _KvRow(
                    k: 'Stack', v: 'Flutter // Spring Boot // Python AirSim'),
                _KvRow(
                    k: 'Operator role',
                    v: 'RESEARCHER  //  full pipeline access'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _bridgeAction(String label, Future<bool> Function() op) async {
    setState(() => _bridgeBusy = true);
    final ok = await op();
    if (!mounted) return;
    setState(() => _bridgeBusy = false);
    ref.read(notificationCenterProvider).push(
          ok ? NoticeLevel.success : NoticeLevel.error,
          ok ? 'Bridge $label requested' : 'Bridge $label failed',
          body: ok
              ? 'Backend accepted the bridge $label command.'
              : 'Backend rejected or could not run the $label command.',
          dedupeKey: 'bridge.$label',
        );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final List<Widget> children;
  final Widget? trailing;
  const _Section({required this.title, required this.children, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel,
        border: Border.all(color: AppColors.line, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: AppColors.line, width: 1),
              ),
            ),
            child: Row(
              children: [
                Text(title,
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 11,
                      letterSpacing: 2.4,
                      fontWeight: FontWeight.w600,
                    )),
                const Spacer(),
                if (trailing != null) trailing!,
              ],
            ),
          ),
          ...children,
        ],
      ),
    );
  }
}

class _KvRow extends StatelessWidget {
  final String k;
  final String v;
  final Color? valueColor;
  const _KvRow({required this.k, required this.v, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.line, width: 0.5)),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 180,
            child: Text(k.toUpperCase(),
                style: const TextStyle(
                  color: AppColors.textMute,
                  fontSize: 10,
                  letterSpacing: 1.4,
                  fontWeight: FontWeight.w500,
                )),
          ),
          Expanded(
            child: SelectableText(
              v,
              style: TextStyle(
                color: valueColor ?? AppColors.textDim,
                fontSize: 11,
                letterSpacing: 0.6,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  final String label;
  final String description;
  final bool value;
  final ValueChanged<bool> onChanged;
  const _SwitchRow({
    required this.label,
    required this.description,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.line, width: 0.5)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    )),
                const SizedBox(height: 2),
                Text(description,
                    style: const TextStyle(
                      color: AppColors.textMute,
                      fontSize: 10,
                      height: 1.35,
                    )),
              ],
            ),
          ),
          Switch.adaptive(
            value: value,
            onChanged: onChanged,
            activeColor: AppColors.accent,
          ),
        ],
      ),
    );
  }
}

class _Btn extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool danger;
  const _Btn(
      {required this.label,
      required this.icon,
      required this.onPressed,
      this.danger = false});

  @override
  Widget build(BuildContext context) {
    final color = danger ? AppColors.alert : AppColors.accent;
    final disabled = onPressed == null;
    return InkWell(
      onTap: onPressed,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: AppColors.panel2,
          border:
              Border.all(color: disabled ? AppColors.line2 : color, width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 13, color: disabled ? AppColors.textMute : color),
            const SizedBox(width: 8),
            Text(label,
                style: TextStyle(
                  color: disabled ? AppColors.textMute : color,
                  fontSize: 10,
                  letterSpacing: 1.6,
                  fontWeight: FontWeight.w600,
                )),
          ],
        ),
      ),
    );
  }
}
