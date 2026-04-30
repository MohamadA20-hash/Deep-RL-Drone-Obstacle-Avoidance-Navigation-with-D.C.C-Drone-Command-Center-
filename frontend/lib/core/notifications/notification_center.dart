import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/bridge_status.dart';
import '../services/telemetry_websocket_service.dart';
import '../state/fleet_providers.dart';
import '../../ui/theme.dart';

enum NoticeLevel { info, success, warn, error }

class Notice {
  final String id;
  final NoticeLevel level;
  final String title;
  final String? body;
  final DateTime at;
  Notice({
    required this.id,
    required this.level,
    required this.title,
    this.body,
    DateTime? at,
  }) : at = at ?? DateTime.now();
}

/// In-app notification bus. Surfaces system events to operators via:
///   - a transient toast (bottom-right, auto-dismisses after 6s)
///   - a persistent history queue (last 50) accessible from the topbar bell
///
/// Sources of notifications:
///   - bridge online/offline transitions
///   - WebSocket connect/disconnect transitions
///   - explicit pushes from command/nav repositories on failure
class NotificationCenter extends ChangeNotifier {
  static const int maxHistory = 50;
  static const Duration toastDuration = Duration(seconds: 6);

  final Queue<Notice> _history = Queue<Notice>();
  Notice? _current;
  Timer? _dismiss;
  int _seq = 0;

  /// Coalesce repeated notices with the same dedupe key inside this window.
  final Map<String, DateTime> _dedupe = {};

  List<Notice> get history => List.unmodifiable(_history);
  Notice? get current => _current;
  int get unreadCount => _unread;
  int _unread = 0;

  void markAllRead() {
    if (_unread == 0) return;
    _unread = 0;
    notifyListeners();
  }

  void push(NoticeLevel level, String title,
      {String? body, String? dedupeKey, Duration? coalesceWindow}) {
    final key = dedupeKey ?? '$level|$title';
    final window = coalesceWindow ?? const Duration(seconds: 8);
    final now = DateTime.now();
    final last = _dedupe[key];
    if (last != null && now.difference(last) < window) {
      return;
    }
    _dedupe[key] = now;

    final n = Notice(
      id: '${now.microsecondsSinceEpoch}-${_seq++}',
      level: level,
      title: title,
      body: body,
    );
    _history.addFirst(n);
    while (_history.length > maxHistory) {
      _history.removeLast();
    }
    _unread++;
    _current = n;
    _dismiss?.cancel();
    _dismiss = Timer(toastDuration, () {
      if (_current?.id == n.id) {
        _current = null;
        notifyListeners();
      }
    });
    notifyListeners();
  }

  void dismissCurrent() {
    if (_current == null) return;
    _current = null;
    _dismiss?.cancel();
    notifyListeners();
  }

  void clearHistory() {
    _history.clear();
    _unread = 0;
    notifyListeners();
  }

  @override
  void dispose() {
    _dismiss?.cancel();
    super.dispose();
  }
}

final notificationCenterProvider =
    ChangeNotifierProvider<NotificationCenter>((_) => NotificationCenter());

// ── Auto-listeners ─────────────────────────────────────────────────────────
//
// `notificationListenersProvider` wires Riverpod state changes (bridge,
// websocket, AirSim streaming) into the notification bus. Read it once near
// the app root via `ref.watch(notificationListenersProvider);` so the
// listeners stay alive for the session.

final notificationListenersProvider = Provider<void>((ref) {
  final nc = ref.read(notificationCenterProvider);

  // Bridge online/offline transitions.
  BridgeUiState? lastBridge;
  ref.listen<BridgeUiState>(bridgeUiStateProvider, (_, next) {
    if (lastBridge != null && lastBridge != next) {
      switch (next) {
        case BridgeUiState.online:
          nc.push(NoticeLevel.success, 'AIRSIM bridge online',
              body: 'Live telemetry stream restored.',
              dedupeKey: 'bridge.online');
          break;
        case BridgeUiState.offline:
          nc.push(NoticeLevel.error, 'AIRSIM bridge offline',
              body: 'Bridge process is not running. Telemetry frozen.',
              dedupeKey: 'bridge.offline');
          break;
        case BridgeUiState.searching:
          nc.push(NoticeLevel.warn, 'Searching for AirSim',
              body: 'Bridge running, waiting for AirSim simulator.',
              dedupeKey: 'bridge.searching');
          break;
        case BridgeUiState.unknown:
          break;
      }
    }
    lastBridge = next;
  });

  // Telemetry websocket lifecycle.
  final wsListenable = ref.read(wsConnectionProvider);
  WsConnectionState lastWs = wsListenable.value;
  void onWs() {
    final s = wsListenable.value;
    if (s == lastWs) return;
    if (s == WsConnectionState.connected &&
        lastWs != WsConnectionState.connected) {
      nc.push(NoticeLevel.success, 'Command link established',
          body: 'WebSocket telemetry channel connected.',
          dedupeKey: 'ws.connected');
    } else if (s == WsConnectionState.error ||
        (s == WsConnectionState.disconnected &&
            lastWs == WsConnectionState.connected)) {
      nc.push(NoticeLevel.warn, 'Command link interrupted',
          body: 'Reconnecting to backend telemetry channel…',
          dedupeKey: 'ws.dropped');
    }
    lastWs = s;
  }

  wsListenable.addListener(onWs);
  ref.onDispose(() => wsListenable.removeListener(onWs));
});

// ── UI ─────────────────────────────────────────────────────────────────────

/// Wraps a child with the floating toast overlay. Mount once near the root.
class NotificationOverlay extends ConsumerWidget {
  final Widget child;
  const NotificationOverlay({super.key, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Activate the auto-listeners (bridge / ws → notifications).
    ref.watch(notificationListenersProvider);
    final nc = ref.watch(notificationCenterProvider);
    return Stack(
      children: [
        child,
        if (nc.current != null)
          Positioned(
            right: 18,
            bottom: 18,
            child: _ToastCard(
              notice: nc.current!,
              onClose: nc.dismissCurrent,
            ),
          ),
      ],
    );
  }
}

class _ToastCard extends StatelessWidget {
  final Notice notice;
  final VoidCallback onClose;
  const _ToastCard({required this.notice, required this.onClose});

  @override
  Widget build(BuildContext context) {
    final accent = _accentFor(notice.level);
    return Material(
      color: Colors.transparent,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 360),
        decoration: BoxDecoration(
          color: AppColors.panel,
          border: Border(
            left: BorderSide(color: accent, width: 3),
            top: const BorderSide(color: AppColors.line, width: 1),
            right: const BorderSide(color: AppColors.line, width: 1),
            bottom: const BorderSide(color: AppColors.line, width: 1),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(14, 10, 8, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(_iconFor(notice.level), size: 14, color: accent),
            const SizedBox(width: 10),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(notice.title.toUpperCase(),
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 11,
                        letterSpacing: 1.3,
                        fontWeight: FontWeight.w600,
                      )),
                  if (notice.body != null) ...[
                    const SizedBox(height: 4),
                    Text(notice.body!,
                        style: const TextStyle(
                          color: AppColors.textDim,
                          fontSize: 10.5,
                          height: 1.35,
                        )),
                  ],
                ],
              ),
            ),
            InkWell(
              onTap: onClose,
              child: const Padding(
                padding: EdgeInsets.all(4),
                child: Icon(Icons.close, size: 12, color: AppColors.textMute),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

IconData _iconFor(NoticeLevel l) => switch (l) {
      NoticeLevel.info => Icons.info_outline,
      NoticeLevel.success => Icons.check_circle_outline,
      NoticeLevel.warn => Icons.warning_amber_outlined,
      NoticeLevel.error => Icons.error_outline,
    };

Color _accentFor(NoticeLevel l) => switch (l) {
      NoticeLevel.info => AppColors.accent,
      NoticeLevel.success => AppColors.ok,
      NoticeLevel.warn => AppColors.warn,
      NoticeLevel.error => AppColors.alert,
    };

/// Topbar bell icon + notification history dropdown.
class NotificationBell extends ConsumerWidget {
  const NotificationBell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final nc = ref.watch(notificationCenterProvider);
    return Tooltip(
      message: 'Notifications (${nc.history.length})',
      child: Material(
        color: AppColors.panel2,
        child: InkWell(
          onTap: () => _showHistory(context, ref),
          child: Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              border: Border.all(color: AppColors.line2, width: 1),
            ),
            alignment: Alignment.center,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                const Icon(Icons.notifications_none,
                    size: 14, color: AppColors.textDim),
                if (nc.unreadCount > 0)
                  Positioned(
                    right: -4,
                    top: -4,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 4, vertical: 1),
                      decoration: BoxDecoration(
                        color: AppColors.alert,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      constraints: const BoxConstraints(minWidth: 14),
                      child: Text(
                        nc.unreadCount > 9 ? '9+' : '${nc.unreadCount}',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 8.5,
                          fontWeight: FontWeight.w700,
                        ),
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

  void _showHistory(BuildContext context, WidgetRef ref) {
    final nc = ref.read(notificationCenterProvider);
    nc.markAllRead();
    showDialog<void>(
      context: context,
      barrierColor: Colors.black54,
      builder: (_) => Dialog(
        alignment: Alignment.topRight,
        insetPadding: const EdgeInsets.only(top: 64, right: 24, left: 24),
        backgroundColor: AppColors.panel,
        shape: const RoundedRectangleBorder(
          side: BorderSide(color: AppColors.line2, width: 1),
        ),
        child: SizedBox(
          width: 420,
          child: AnimatedBuilder(
            animation: nc,
            builder: (_, __) => Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: const BoxDecoration(
                    border: Border(
                      bottom: BorderSide(color: AppColors.line, width: 1),
                    ),
                  ),
                  child: Row(
                    children: [
                      const Text('NOTIFICATIONS',
                          style: TextStyle(
                            color: AppColors.text,
                            fontSize: 11,
                            letterSpacing: 2,
                            fontWeight: FontWeight.w600,
                          )),
                      const Spacer(),
                      InkWell(
                        onTap: nc.clearHistory,
                        child: const Padding(
                          padding: EdgeInsets.all(6),
                          child: Text('CLEAR',
                              style: TextStyle(
                                color: AppColors.textMute,
                                fontSize: 9,
                                letterSpacing: 1.4,
                              )),
                        ),
                      ),
                    ],
                  ),
                ),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 480),
                  child: nc.history.isEmpty
                      ? const Padding(
                          padding: EdgeInsets.symmetric(vertical: 36),
                          child: Text('NO EVENTS',
                              style: TextStyle(
                                color: AppColors.textMute,
                                fontSize: 10,
                                letterSpacing: 2,
                              )),
                        )
                      : ListView.builder(
                          shrinkWrap: true,
                          itemCount: nc.history.length,
                          itemBuilder: (_, i) {
                            final n = nc.history[i];
                            final accent = _accentFor(n.level);
                            return Container(
                              padding:
                                  const EdgeInsets.fromLTRB(14, 10, 14, 10),
                              decoration: const BoxDecoration(
                                border: Border(
                                  bottom: BorderSide(
                                      color: AppColors.line, width: 1),
                                ),
                              ),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.only(top: 2),
                                    child: Icon(_iconFor(n.level),
                                        size: 12, color: accent),
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(n.title,
                                            style: const TextStyle(
                                              color: AppColors.text,
                                              fontSize: 11,
                                              fontWeight: FontWeight.w600,
                                            )),
                                        if (n.body != null) ...[
                                          const SizedBox(height: 2),
                                          Text(n.body!,
                                              style: const TextStyle(
                                                color: AppColors.textDim,
                                                fontSize: 10,
                                                height: 1.35,
                                              )),
                                        ],
                                        const SizedBox(height: 3),
                                        Text(_fmt(n.at),
                                            style: const TextStyle(
                                              color: AppColors.textMute,
                                              fontSize: 9,
                                              letterSpacing: 1.0,
                                            )),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String _fmt(DateTime d) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(d.hour)}:${two(d.minute)}:${two(d.second)}';
  }
}
