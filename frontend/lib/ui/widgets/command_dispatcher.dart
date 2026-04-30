import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/command.dart';
import '../../core/repositories/command_repository.dart';
import '../../core/state/fleet_providers.dart';

/// Shared helper for the dashboard's control buttons. Sends a command to the
/// currently-selected drone and surfaces success/failure as a SnackBar so
/// operators get immediate confirmation that the action was queued.
class CommandDispatcher {
  CommandDispatcher(this._ref, this._context);

  final WidgetRef _ref;
  final BuildContext _context;

  Future<void> send(
    DroneCommandType type, {
    String? parameters,
    String? successLabel,
  }) async {
    final drone = _ref.read(selectedDroneProvider);
    if (drone == null) {
      _toast('NO DRONE SELECTED', error: true);
      return;
    }
    final repo = _ref.read(commandRepositoryProvider);
    try {
      final cmd = await repo.send(DroneCommand(
        droneId: drone.id,
        type: type,
        parameters: parameters,
      ));
      _toast(
        '${(successLabel ?? type.wire)} QUEUED · ${cmd.id?.substring(0, 8) ?? ''}',
      );
    } on DioException catch (e) {
      final body = e.response?.data;
      String msg = e.message ?? 'Command failed';
      if (body is Map && body['message'] is String) {
        msg = body['message'] as String;
      }
      _toast('${type.wire} REJECTED · $msg', error: true);
    }
  }

  void _toast(String text, {bool error = false}) {
    if (!_context.mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(_context);
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(SnackBar(
      duration: const Duration(seconds: 3),
      backgroundColor:
          error ? const Color(0xFF7A1F1F) : const Color(0xFF1F2A33),
      content: Text(
        text,
        style: const TextStyle(
          fontSize: 11,
          letterSpacing: 1.4,
          fontWeight: FontWeight.w600,
        ),
      ),
    ));
  }
}
