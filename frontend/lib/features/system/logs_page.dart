import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/notifications/notification_center.dart';
import '../../core/repositories/logs_repository.dart';
import '../../ui/theme.dart';
import '../../ui/widgets/app_shell.dart';

/// Operator-facing log viewer. Polls `GET /api/logs/recent` every 2 s and
/// renders entries in a virtualized list with level + text filtering.
class LogsPage extends ConsumerStatefulWidget {
  const LogsPage({super.key});

  @override
  ConsumerState<LogsPage> createState() => _LogsPageState();
}

class _LogsPageState extends ConsumerState<LogsPage> {
  static const Duration _pollInterval = Duration(seconds: 2);

  Timer? _timer;
  bool _busy = false;
  bool _autoRefresh = true;
  bool _autoScroll = true;
  String _level = 'ALL';
  String _query = '';
  int _limit = 300;

  LogsResult _result = LogsResult(entries: const [], exists: true, path: '');
  String? _lastError;

  final ScrollController _scrollController = ScrollController();
  final TextEditingController _searchController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _refresh();
    _restartTimer();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scrollController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  void _restartTimer() {
    _timer?.cancel();
    if (!_autoRefresh) return;
    _timer = Timer.periodic(_pollInterval, (_) => _refresh());
  }

  Future<void> _refresh() async {
    if (_busy) return;
    _busy = true;
    try {
      final r = await ref
          .read(logsRepositoryProvider)
          .recent(limit: _limit, level: _level, q: _query);
      if (!mounted) return;
      setState(() {
        _result = r;
        _lastError = r.exists ? null : 'log file not found';
      });
      if (_autoScroll && _scrollController.hasClients) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController
                .jumpTo(_scrollController.position.maxScrollExtent);
          }
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _lastError = e.toString());
      }
    } finally {
      _busy = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      activeRoute: 'logs',
      title: 'System Logs',
      subtitle: 'Backend rolling log // last $_limit lines',
      trailing: _HeaderControls(
        autoRefresh: _autoRefresh,
        onAutoRefresh: (v) {
          setState(() => _autoRefresh = v);
          _restartTimer();
        },
        autoScroll: _autoScroll,
        onAutoScroll: (v) => setState(() => _autoScroll = v),
        onRefresh: _refresh,
      ),
      child: Column(
        children: [
          _FilterRow(
            level: _level,
            limit: _limit,
            controller: _searchController,
            onLevel: (l) {
              setState(() => _level = l);
              _refresh();
            },
            onLimit: (l) {
              setState(() => _limit = l);
              _refresh();
            },
            onQuery: (q) {
              setState(() => _query = q);
              _refresh();
            },
            onCopy: () async {
              final buf = _result.entries
                  .map((e) =>
                      '${e.ts}  ${e.level.padRight(5)}  ${e.logger}  ${e.message}${e.stack == null ? '' : '\n${e.stack}'}')
                  .join('\n');
              await Clipboard.setData(ClipboardData(text: buf));
              if (!mounted) return;
              ref.read(notificationCenterProvider).push(
                    NoticeLevel.success,
                    'Copied ${_result.entries.length} log lines',
                    dedupeKey: 'logs.copy',
                  );
            },
          ),
          const SizedBox(height: 8),
          if (_lastError != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              margin: const EdgeInsets.only(bottom: 8),
              decoration: BoxDecoration(
                color: AppColors.panel,
                border: Border.all(color: AppColors.alert, width: 1),
              ),
              child: Text('LOG TAIL ERROR  //  ${_lastError!}',
                  style: const TextStyle(
                    color: AppColors.alert,
                    fontSize: 10.5,
                    letterSpacing: 1.4,
                  )),
            ),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.panel,
                border: Border.all(color: AppColors.line, width: 1),
              ),
              child: _result.entries.isEmpty
                  ? const Center(
                      child: Text('— NO LOG ENTRIES —',
                          style: TextStyle(
                            color: AppColors.textMute,
                            fontSize: 11,
                            letterSpacing: 2,
                          )),
                    )
                  : Scrollbar(
                      controller: _scrollController,
                      thumbVisibility: true,
                      child: ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        itemCount: _result.entries.length,
                        itemBuilder: (_, i) {
                          // entries are already newest-first from backend
                          final e =
                              _result.entries[_result.entries.length - 1 - i];
                          return _LogRow(entry: e);
                        },
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderControls extends StatelessWidget {
  final bool autoRefresh;
  final ValueChanged<bool> onAutoRefresh;
  final bool autoScroll;
  final ValueChanged<bool> onAutoScroll;
  final VoidCallback onRefresh;
  const _HeaderControls({
    required this.autoRefresh,
    required this.onAutoRefresh,
    required this.autoScroll,
    required this.onAutoScroll,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _ToggleChip(
            label: 'AUTOPULL',
            on: autoRefresh,
            onTap: () => onAutoRefresh(!autoRefresh)),
        const SizedBox(width: 8),
        _ToggleChip(
            label: 'TAIL',
            on: autoScroll,
            onTap: () => onAutoScroll(!autoScroll)),
        const SizedBox(width: 8),
        _IconBtn(icon: Icons.refresh, tooltip: 'Refresh now', onTap: onRefresh),
      ],
    );
  }
}

class _ToggleChip extends StatelessWidget {
  final String label;
  final bool on;
  final VoidCallback onTap;
  const _ToggleChip(
      {required this.label, required this.on, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: on ? AppColors.accentSoft : AppColors.panel2,
          border: Border.all(
              color: on ? AppColors.accent : AppColors.line2, width: 1),
        ),
        child: Text(label,
            style: TextStyle(
              color: on ? AppColors.accent : AppColors.textDim,
              fontSize: 9.5,
              letterSpacing: 1.5,
              fontWeight: FontWeight.w600,
            )),
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  const _IconBtn(
      {required this.icon, required this.tooltip, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        child: Container(
          width: 30,
          height: 28,
          decoration: BoxDecoration(
            color: AppColors.panel2,
            border: Border.all(color: AppColors.line2, width: 1),
          ),
          alignment: Alignment.center,
          child: Icon(icon, size: 13, color: AppColors.textDim),
        ),
      ),
    );
  }
}

class _FilterRow extends StatelessWidget {
  final String level;
  final int limit;
  final TextEditingController controller;
  final ValueChanged<String> onLevel;
  final ValueChanged<int> onLimit;
  final ValueChanged<String> onQuery;
  final VoidCallback onCopy;
  const _FilterRow({
    required this.level,
    required this.limit,
    required this.controller,
    required this.onLevel,
    required this.onLimit,
    required this.onQuery,
    required this.onCopy,
  });

  @override
  Widget build(BuildContext context) {
    const levels = ['ALL', 'INFO', 'WARN', 'ERROR', 'DEBUG'];
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.panel,
        border: Border.all(color: AppColors.line, width: 1),
      ),
      child: Row(
        children: [
          ...levels.map((l) => Padding(
                padding: const EdgeInsets.only(right: 6),
                child: _ToggleChip(
                    label: l, on: level == l, onTap: () => onLevel(l)),
              )),
          const SizedBox(width: 12),
          SizedBox(
            width: 240,
            height: 28,
            child: TextField(
              controller: controller,
              style: const TextStyle(color: AppColors.text, fontSize: 11),
              cursorColor: AppColors.accent,
              decoration: InputDecoration(
                isDense: true,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                hintText: 'search…',
                hintStyle:
                    const TextStyle(color: AppColors.textMute, fontSize: 11),
                filled: true,
                fillColor: AppColors.panel2,
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(2),
                  borderSide:
                      const BorderSide(color: AppColors.line2, width: 1),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(2),
                  borderSide:
                      const BorderSide(color: AppColors.accent, width: 1),
                ),
              ),
              onSubmitted: onQuery,
              onChanged: (v) {
                // small debounce: only push every change >= 3 chars or empty
                if (v.isEmpty || v.length >= 3) onQuery(v);
              },
            ),
          ),
          const Spacer(),
          const Text('LIMIT',
              style: TextStyle(
                color: AppColors.textMute,
                fontSize: 9,
                letterSpacing: 1.4,
              )),
          const SizedBox(width: 6),
          DropdownButton<int>(
            value: limit,
            dropdownColor: AppColors.panel,
            iconEnabledColor: AppColors.textDim,
            underline: const SizedBox.shrink(),
            style: const TextStyle(
                color: AppColors.text, fontSize: 11, letterSpacing: 1.0),
            items: const [100, 200, 300, 500, 1000, 2000]
                .map((v) => DropdownMenuItem(value: v, child: Text('$v')))
                .toList(),
            onChanged: (v) {
              if (v != null) onLimit(v);
            },
          ),
          const SizedBox(width: 8),
          _IconBtn(
              icon: Icons.copy_all_outlined,
              tooltip: 'Copy visible logs',
              onTap: onCopy),
        ],
      ),
    );
  }
}

class _LogRow extends StatelessWidget {
  final LogEntry entry;
  const _LogRow({required this.entry});

  @override
  Widget build(BuildContext context) {
    final color = switch (entry.level) {
      'ERROR' => AppColors.alert,
      'WARN' => AppColors.warn,
      'DEBUG' => AppColors.textMute,
      'TRACE' => AppColors.textMute,
      _ => AppColors.textDim,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.line, width: 0.5)),
      ),
      child: DefaultTextStyle(
        style: const TextStyle(
          fontFamily: 'Courier',
          fontSize: 11,
          color: AppColors.text,
          height: 1.35,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 92,
                  child: Text(
                    entry.ts.length >= 12
                        ? entry.ts.substring(11, 23)
                        : entry.ts,
                    style: const TextStyle(
                        color: AppColors.textMute, fontSize: 10.5),
                  ),
                ),
                SizedBox(
                  width: 56,
                  child: Text(entry.level,
                      style: TextStyle(
                        color: color,
                        fontWeight: FontWeight.w700,
                        fontSize: 10.5,
                      )),
                ),
                SizedBox(
                  width: 220,
                  child: Text(
                    entry.logger,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: AppColors.textDim, fontSize: 10.5),
                  ),
                ),
                Expanded(
                  child: SelectableText(
                    entry.message,
                    style: const TextStyle(color: AppColors.text, fontSize: 11),
                  ),
                ),
              ],
            ),
            if (entry.stack != null) ...[
              const SizedBox(height: 2),
              Padding(
                padding: const EdgeInsets.only(left: 92),
                child: SelectableText(
                  entry.stack!,
                  style: const TextStyle(
                    color: AppColors.alert,
                    fontSize: 10.5,
                    fontFamily: 'Courier',
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
