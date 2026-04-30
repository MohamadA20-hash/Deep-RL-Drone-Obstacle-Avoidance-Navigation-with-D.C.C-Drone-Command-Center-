import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:vector_math/vector_math_64.dart' as vmath;
import 'dart:math' as math;
import '../../core/models/telemetry.dart';
import '../../core/notifications/notification_center.dart';
import '../../core/repositories/bridge_repository.dart';
import '../../core/services/telemetry_websocket_service.dart';
import '../../core/state/fleet_providers.dart';
import '../theme.dart';
import 'panel_card.dart';

/// A pending navigation goal in AirSim NED meters (north, east).
/// Set by tapping the map; consumed by the START NAV button.
class NedGoal {
  final double north;
  final double east;
  const NedGoal(this.north, this.east);
}

/// Riverpod state for the goal that was last placed on the map but not yet
/// dispatched to the autonomy stack. The map writes here on tap; the right
/// panel reads it when START NAV is pressed.
final pendingGoalProvider = StateProvider<NedGoal?>((ref) => null);

/// Live cursor position over the map, in NED meters. Updated on hover
/// (desktop) or last tap (touch). Consumed by [_CoordReadout].
final cursorNedProvider = StateProvider<NedGoal?>((ref) => null);

/// SIM WORLD MAP — interactive cartographic view in Palantir / Anduril style.
/// Vector terrain (contours), hex grid, building footprints, drone glyph
/// with heading + FOV cone + flight trail, AOI polygon, scale bar, compass
/// rose, edge coordinate ticks. Pan / zoom via InteractiveViewer; tap to
/// place a waypoint.
class SimWorldMap extends ConsumerStatefulWidget {
  const SimWorldMap({super.key});

  @override
  ConsumerState<SimWorldMap> createState() => _SimWorldMapState();
}

class _SimWorldMapState extends ConsumerState<SimWorldMap> {
  final TransformationController _xform = TransformationController();
  String _layer = 'VECTOR';
  bool _sendingGoal = false;

  /// Map display spans ±[_nedSpanMeters/2] m in N/E around origin.
  /// MUST equal `_MapPainter.kNedSpan`.
  static const double _nedSpanMeters = 100.0;

  /// Permitted zoom range for the InteractiveViewer.
  static const double _minScale = 0.4;
  static const double _maxScale = 8.0;

  @override
  void dispose() {
    _xform.dispose();
    super.dispose();
  }

  /// Multiplicative zoom that PRESERVES the current pan and zooms toward
  /// the centre of the visible viewport (rather than collapsing back to the
  /// origin like `setIdentity()` did).
  void _zoom(double factor) {
    final m = _xform.value.clone();
    final current = m.getMaxScaleOnAxis();
    final target = (current * factor).clamp(_minScale, _maxScale);
    final effective = target / current;
    if ((effective - 1.0).abs() < 1e-4) return;
    // Find a stable focal point — the centre of the rendered widget — and
    // scale around it so the user doesn't lose their place.
    final box = context.findRenderObject() as RenderBox?;
    final size = box?.size ?? const Size(800, 600);
    final focal = Offset(size.width / 2, size.height / 2);
    // Translate focal to origin, scale, translate back.
    m.translate(focal.dx, focal.dy);
    m.scale(effective, effective);
    m.translate(-focal.dx, -focal.dy);
    setState(() => _xform.value = m);
  }

  /// Tap handler: converts the tap pixel to NED coordinates, stores the
  /// goal locally and on the backend (without starting navigation), and
  /// publishes it to [pendingGoalProvider] so the right panel's START NAV
  /// button can pick it up.
  ///
  /// IMPORTANT: tapping NEVER starts navigation. The user must press
  /// START NAV explicitly. This matches the operator-grade workflow:
  ///   1. tap to set goal
  ///   2. inspect / adjust
  ///   3. press START NAV to engage autonomy
  Future<void> _handleMapTap(Offset p, Size mapSize) async {
    // Tap-to-set-goal must NEVER be permanently locked. If a previous send
    // is still mid-flight we still update the local pin (operator gets
    // visual feedback) but skip the backend POST. The lock auto-releases
    // via the timeout/finally below.
    final fx = p.dx / mapSize.width;
    final fy = p.dy / mapSize.height;
    final nedY = (fx - 0.5) * _nedSpanMeters; // East
    final nedX = (0.5 - fy) * _nedSpanMeters; // North

    debugPrint(
        '[map] tap @ pixel=$p size=$mapSize -> NED N=${nedX.toStringAsFixed(2)} E=${nedY.toStringAsFixed(2)}');
    ref.read(pendingGoalProvider.notifier).state = NedGoal(nedX, nedY);

    if (_sendingGoal) {
      _toast('Pin moved · previous goal still sending…');
      return;
    }

    final droneId = ref.read(selectedDroneIdProvider) ??
        ref.read(selectedDroneProvider)?.id;
    if (droneId == null) {
      _toast('Goal set locally — no drone selected');
      return;
    }

    setState(() => _sendingGoal = true);
    try {
      final ok = await ref
          .read(bridgeRepositoryProvider)
          .setGoal(
            droneId: droneId,
            goalX: double.parse(nedX.toStringAsFixed(2)),
            goalY: double.parse(nedY.toStringAsFixed(2)),
          )
          // Hard timeout so a slow / wedged backend call can NEVER leave
          // _sendingGoal=true and lock the map out for the rest of the
          // session. The local pendingGoalProvider was already updated
          // above, so the operator still sees their pin.
          .timeout(const Duration(seconds: 4), onTimeout: () => false);
      if (ok) {
        _toast(
            'GOAL SET → N=${nedX.toStringAsFixed(1)} E=${nedY.toStringAsFixed(1)} · press START NAV');
      } else {
        _toast('Goal set locally · backend timeout/rejected');
      }
    } catch (e) {
      _toast('Goal failed: $e');
    } finally {
      if (mounted) setState(() => _sendingGoal = false);
    }
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(fontSize: 12)),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
      ),
    );
    final upper = msg.toUpperCase();
    final level = upper.contains('FAIL') ||
            upper.contains('ERROR') ||
            upper.contains('REJECT')
        ? NoticeLevel.error
        : (upper.contains('WARN') || upper.contains('NOT '))
            ? NoticeLevel.warn
            : NoticeLevel.info;
    ref.read(notificationCenterProvider).push(level, 'Map', body: msg);
  }

  @override
  Widget build(BuildContext context) {
    return PanelCard(
      padding: const EdgeInsets.all(0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _MapToolbar(
            layer: _layer,
            onLayer: (l) => setState(() => _layer = l),
            onZoomIn: () => _zoom(1.25),
            onZoomOut: () => _zoom(0.8),
          ),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: _MapSurface(
                    xform: _xform,
                    onTap: _handleMapTap,
                    layer: _layer,
                  ),
                ),
                const _RightPanel(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// Toolbar
// ============================================================
class _MapToolbar extends StatelessWidget {
  final String layer;
  final ValueChanged<String> onLayer;
  final VoidCallback onZoomIn;
  final VoidCallback onZoomOut;
  const _MapToolbar({
    required this.layer,
    required this.onLayer,
    required this.onZoomIn,
    required this.onZoomOut,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.line)),
      ),
      child: Row(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              Text('TACTICAL MAP', style: AppText.cardTitle),
              SizedBox(height: 3),
              Text('NED // WGS-84 // KING CO, WA', style: AppText.cardSub),
            ],
          ),
          const SizedBox(width: 18),
          // Layer chips
          _LayerSeg(value: layer, onChanged: onLayer),
          const SizedBox(width: 10),
          // Search box
          Expanded(
            child: Container(
              height: 28,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                color: AppColors.panel2,
                border: Border.all(color: AppColors.line2),
              ),
              child: Row(
                children: const [
                  Icon(Icons.search, size: 13, color: AppColors.textMute),
                  SizedBox(width: 8),
                  Text('Search coord, MGRS, asset…',
                      style: TextStyle(
                        color: AppColors.textMute,
                        fontSize: 11,
                        letterSpacing: 0.4,
                      )),
                ],
              ),
            ),
          ),
          const SizedBox(width: 10),
          _IconBtn(icon: Icons.add, onTap: onZoomIn),
          const SizedBox(width: 6),
          _IconBtn(icon: Icons.remove, onTap: onZoomOut),
          const SizedBox(width: 6),
          const _IconBtn(icon: Icons.center_focus_weak),
          const SizedBox(width: 6),
          const _IconBtn(icon: Icons.fullscreen),
        ],
      ),
    );
  }
}

class _LayerSeg extends StatelessWidget {
  final String value;
  final ValueChanged<String> onChanged;
  const _LayerSeg({required this.value, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel2,
        border: Border.all(color: AppColors.line2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: ['VECTOR', 'SAT', 'TERRAIN'].map((t) {
          final active = t == value;
          return GestureDetector(
            onTap: () => onChanged(t),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: active ? AppColors.panel3 : Colors.transparent,
                border: active
                    ? const Border(
                        bottom: BorderSide(color: AppColors.accent, width: 1.5))
                    : null,
              ),
              child: Text(
                t,
                style: TextStyle(
                  color: active ? AppColors.text : AppColors.textMute,
                  fontSize: 9.5,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.4,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  const _IconBtn({required this.icon, this.onTap});
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          color: AppColors.panel2,
          border: Border.all(color: AppColors.line2),
        ),
        child: Icon(icon, size: 14, color: AppColors.textDim),
      ),
    );
  }
}

// ============================================================
// Map surface
// ============================================================

/// One timestamped raw heading reading; used by the signed yaw-window
/// rotation detector inside `_MapSurfaceState`.
class _HeadingSample {
  final DateTime t;
  final double deg;
  const _HeadingSample(this.t, this.deg);
}

class _MapSurface extends ConsumerStatefulWidget {
  final TransformationController xform;
  final void Function(Offset position, Size mapSize) onTap;
  final String layer;

  const _MapSurface({
    required this.xform,
    required this.onTap,
    required this.layer,
  });

  @override
  ConsumerState<_MapSurface> createState() => _MapSurfaceState();
}

class _MapSurfaceState extends ConsumerState<_MapSurface> {
  // Raw-pointer tap tracking. We bypass the gesture arena (InteractiveViewer
  // would otherwise win and swallow taps) by listening directly via
  // ``Listener`` and synthesising a tap when pointer-down -> pointer-up
  // travels less than ``_kTapSlop`` pixels.
  Offset? _downPos;
  static const double _kTapSlop = 18.0; // generous click radius

  // AirSim's raw yaw and NED position both jitter every frame. We need to
  // distinguish three regimes reliably:
  //   * hover         -> heading must be ROCK still
  //   * translating   -> heading follows motion direction
  //   * pure rotation -> heading follows yaw even with zero NED motion
  //
  // Two architectural rules keep this stable:
  //   1. Smoothing is done as an **angular** EMA over the shortest signed arc
  //      (`_smDeg`). The previous Cartesian (cos, sin) EMA caused the
  //      magnitude of the unit vector to collapse toward zero during
  //      sustained turns, which made `atan2` numerically unstable and made
  //      the icon spin wildly. Working in angle-space avoids that entirely.
  //   2. State mutation is bound to telemetry arrival, not to `build()`.
  //      `build()` can fire on completely unrelated events (hover, zoom,
  //      provider rebuilds), so doing EMA work there processes the same
  //      frame multiple times and corrupts the smoothing. Listeners are
  //      attached to the underlying `ValueListenable`s in `_attach*` and
  //      the build method only reads the cached, already-smoothed state.
  //
  // Hover-vs-turn detection still uses a signed sliding window of yaw
  // samples: random noise self-cancels (sum stays near 0), real rotations
  // accumulate past a threshold.
  double? _smDeg; // angular EMA state, degrees in [0, 360)
  double? _shownHeadingDeg;
  double? _smPosN;
  double? _smPosE;
  double? _prevSmPosN;
  double? _prevSmPosE;
  List<TrailPoint> _displayTrail = const <TrailPoint>[];
  final List<_HeadingSample> _yawWindow = [];
  bool _isRotating = false;
  int _movingFrames = 0;
  int _stillFrames = 0;
  bool _isMoving = false;
  // Listener bookkeeping so we can detach cleanly on dispose / re-attach if
  // the underlying ValueListenable instance is swapped.
  ValueListenable<Telemetry?>? _attachedTelemetry;
  VoidCallback? _telemetryListener;
  ValueListenable<List<TrailPoint>>? _attachedTrail;
  VoidCallback? _trailListener;
  bool _attachedLive = false;
  static const double _kHeadingAlpha = 0.25;
  static const double _kPosAlpha = 0.15;
  static const double _kMotionGateMeters = 0.25; // per-frame displacement
  static const int _kMotionConfirmFrames = 4;
  static const int _kMotionReleaseFrames = 6;
  static const double _kHeadingDeadbandDeg = 6.0;
  // Signed yaw-window gate.
  static const Duration _kYawWindow = Duration(milliseconds: 1000);
  static const double _kYawTurnThresholdDeg = 12.0;
  static const double _kYawReleaseThresholdDeg = 4.0;

  double _angDiff(double a, double b) {
    var d = (a - b) % 360.0;
    if (d > 180.0) d -= 360.0;
    if (d < -180.0) d += 360.0;
    return d.abs();
  }

  /// Signed shortest-arc delta from `from` to `to` in degrees, range (-180, 180].
  /// Positive = clockwise, negative = counter-clockwise. Robust to 360\u00b0 wrap.
  double _signedAngDelta(double from, double to) {
    var d = (to - from) % 360.0;
    if (d > 180.0) d -= 360.0;
    if (d < -180.0) d += 360.0;
    return d;
  }

  // ----- Listener attachment & lifecycle -----
  //
  // The processing pipeline below is deliberately driven by the underlying
  // ValueListenable callbacks rather than by `build()`, so each frame is
  // processed exactly once even if the widget rebuilds for unrelated
  // reasons (zoom, hover, sibling provider updates).

  void _attachTelemetry(ValueListenable<Telemetry?> src) {
    if (_attachedTelemetry == src) return;
    if (_attachedTelemetry != null && _telemetryListener != null) {
      _attachedTelemetry!.removeListener(_telemetryListener!);
    }
    void onChange() => _processTelemetry(src.value);
    src.addListener(onChange);
    _attachedTelemetry = src;
    _telemetryListener = onChange;
    // Defer the initial seed so we don't call setState during a build.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _processTelemetry(src.value);
    });
  }

  void _attachTrail(ValueListenable<List<TrailPoint>> src) {
    if (_attachedTrail == src) return;
    if (_attachedTrail != null && _trailListener != null) {
      _attachedTrail!.removeListener(_trailListener!);
    }
    void onChange() => _processTrail(src.value);
    src.addListener(onChange);
    _attachedTrail = src;
    _trailListener = onChange;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _processTrail(src.value);
    });
  }

  void _detachAll() {
    if (_attachedTelemetry != null && _telemetryListener != null) {
      _attachedTelemetry!.removeListener(_telemetryListener!);
    }
    if (_attachedTrail != null && _trailListener != null) {
      _attachedTrail!.removeListener(_trailListener!);
    }
    _attachedTelemetry = null;
    _attachedTrail = null;
    _telemetryListener = null;
    _trailListener = null;
  }

  @override
  void dispose() {
    _detachAll();
    super.dispose();
  }

  // ----- Telemetry processing (heading) -----

  void _processTelemetry(Telemetry? t) {
    if (!mounted) return;
    final rawDeg = (_attachedLive && t != null) ? t.headingDeg : null;
    if (rawDeg == null) {
      // AirSim went offline or telemetry cleared; reset filter state but
      // leave _shownHeadingDeg latched so the icon doesn't snap.
      _yawWindow.clear();
      _isRotating = false;
      _smDeg = null;
      return;
    }

    // Signed sliding-window rotation detector. Hover noise oscillates and
    // self-cancels; sustained yaw accumulates past the trip threshold.
    final now = DateTime.now();
    _yawWindow.add(_HeadingSample(now, rawDeg));
    final cutoff = now.subtract(_kYawWindow);
    while (_yawWindow.isNotEmpty && _yawWindow.first.t.isBefore(cutoff)) {
      _yawWindow.removeAt(0);
    }
    double signedSum = 0.0;
    for (int i = 1; i < _yawWindow.length; i++) {
      signedSum += _signedAngDelta(_yawWindow[i - 1].deg, _yawWindow[i].deg);
    }
    final absSum = signedSum.abs();
    if (_isRotating) {
      if (absSum < _kYawReleaseThresholdDeg) _isRotating = false;
    } else {
      if (absSum >= _kYawTurnThresholdDeg) _isRotating = true;
    }

    final allowUpdate = _isMoving || _isRotating;
    final prevShown = _shownHeadingDeg;

    if (!allowUpdate) {
      // Frozen \u2014 latch first sample but do not move thereafter.
      if (_shownHeadingDeg == null) {
        _smDeg = rawDeg;
        _shownHeadingDeg = rawDeg;
      }
    } else {
      // Angular EMA: step toward rawDeg along the *shortest signed arc*.
      // This never collapses magnitude the way Cartesian EMA does.
      if (_smDeg == null) {
        _smDeg = rawDeg;
      } else {
        final delta = _signedAngDelta(_smDeg!, rawDeg);
        var next = _smDeg! + delta * _kHeadingAlpha;
        next = next % 360.0;
        if (next < 0) next += 360.0;
        _smDeg = next;
      }
      final db = _isRotating ? 1.5 : _kHeadingDeadbandDeg;
      if (_shownHeadingDeg == null ||
          _angDiff(_smDeg!, _shownHeadingDeg!) >= db) {
        _shownHeadingDeg = _smDeg;
      }
    }

    if (prevShown != _shownHeadingDeg) {
      setState(() {});
    }
  }

  // ----- Trail processing (position EMA + motion gate) -----

  void _processTrail(List<TrailPoint> raw) {
    if (!mounted) return;
    final source = _attachedLive ? raw : const <TrailPoint>[];
    if (source.isEmpty) {
      _smPosN = null;
      _smPosE = null;
      if (_displayTrail.isNotEmpty) {
        setState(() => _displayTrail = const <TrailPoint>[]);
      }
      return;
    }
    final last = source.last;
    if (_smPosN == null || _smPosE == null) {
      _smPosN = last.north;
      _smPosE = last.east;
    } else {
      _smPosN = _smPosN! + (last.north - _smPosN!) * _kPosAlpha;
      _smPosE = _smPosE! + (last.east - _smPosE!) * _kPosAlpha;
    }

    // Positional motion gate (drives the heading-freeze decision).
    if (_prevSmPosN != null && _prevSmPosE != null) {
      final dn = _smPosN! - _prevSmPosN!;
      final de = _smPosE! - _prevSmPosE!;
      final disp = math.sqrt(dn * dn + de * de);
      if (disp >= _kMotionGateMeters) {
        _movingFrames++;
        _stillFrames = 0;
        if (_movingFrames >= _kMotionConfirmFrames) _isMoving = true;
      } else {
        _stillFrames++;
        _movingFrames = 0;
        if (_stillFrames >= _kMotionReleaseFrames) _isMoving = false;
      }
    }
    _prevSmPosN = _smPosN;
    _prevSmPosE = _smPosE;

    final smoothed = List<TrailPoint>.from(source);
    smoothed[smoothed.length - 1] =
        TrailPoint(_smPosN!, _smPosE!, last.down, last.at);
    setState(() => _displayTrail = smoothed);
  }

  @override
  Widget build(BuildContext context) {
    final ref = this.ref;
    final trailListenable = ref.watch(liveTrailProvider);
    final telemetryListenable = ref.watch(liveTelemetryProvider);
    final live = ref.watch(airsimStreamingProvider).asData?.value ?? false;
    final pendingGoal = ref.watch(pendingGoalProvider);

    // Wire / rewire listeners to the underlying ValueListenables. These calls
    // are idempotent: they only re-attach if the listenable identity changed
    // or if the AirSim live flag flipped (which gates whether incoming frames
    // are treated as real telemetry).
    if (_attachedLive != live) {
      _attachedLive = live;
      // Re-process the latest cached values under the new live flag, but
      // schedule it after the current build so we don't setState mid-build.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _processTelemetry(_attachedTelemetry?.value);
        _processTrail(_attachedTrail?.value ?? const <TrailPoint>[]);
      });
    }
    _attachTelemetry(telemetryListenable);
    _attachTrail(trailListenable);

    final liveTrail = _displayTrail;
    final headingDeg = _shownHeadingDeg;

    return Container(
      color: AppColors.mapBg,
      child: ClipRect(
        child: LayoutBuilder(builder: (context, constraints) {
          final size = Size(constraints.maxWidth, constraints.maxHeight);
          return Builder(
            builder: (context) {
              return Stack(
                children: [
                  // Pannable / zoomable map content. Mobile-friendly:
                  // single-finger drag pans, two-finger pinch zooms,
                  // huge boundary margin so users can pan the map well
                  // off-screen like a Google-Maps viewport.
                  Positioned.fill(
                    child: Listener(
                      // Raw pointer events bypass the gesture arena so
                      // InteractiveViewer's pan recognizer can no longer
                      // swallow tap-ups. Down position recorded; on up
                      // we treat short-distance releases as a tap and
                      // map through the viewer transform.
                      behavior: HitTestBehavior.translucent,
                      onPointerDown: (e) => _downPos = e.localPosition,
                      onPointerUp: (e) {
                        final start = _downPos;
                        _downPos = null;
                        if (start == null) return;
                        if ((e.localPosition - start).distance > _kTapSlop) {
                          return; // it was a drag/pan, not a tap
                        }
                        // Convert viewport-space pointer to scene-space
                        // by inverting the InteractiveViewer matrix.
                        final inv = Matrix4.inverted(widget.xform.value);
                        final v = inv.transform3(vmath.Vector3(
                            e.localPosition.dx, e.localPosition.dy, 0));
                        const m = 2000.0;
                        widget.onTap(
                          Offset(v.x - m, v.y - m),
                          size,
                        );
                      },
                      child: InteractiveViewer(
                        transformationController: widget.xform,
                        minScale: 0.4,
                        maxScale: 8.0,
                        panEnabled: true,
                        scaleEnabled: true,
                        clipBehavior: Clip.none,
                        boundaryMargin: const EdgeInsets.all(2000),
                        child: Builder(builder: (_) {
                          const m = 2000.0;
                          final extended = Size(
                            size.width + m * 2,
                            size.height + m * 2,
                          );
                          // One-shot recentre after first frame: identity
                          // would show the top-left of the extended canvas
                          // (empty grid), so push the centre into view.
                          if (widget.xform.value == Matrix4.identity()) {
                            WidgetsBinding.instance.addPostFrameCallback((_) {
                              if (widget.xform.value == Matrix4.identity()) {
                                widget.xform.value = Matrix4.identity()
                                  ..translate(-m, -m);
                              }
                            });
                          }
                          return SizedBox.fromSize(
                            size: extended,
                            child: MouseRegion(
                              onHover: (e) {
                                final lx = e.localPosition.dx - m;
                                final ly = e.localPosition.dy - m;
                                final fx = lx / size.width;
                                final fy = ly / size.height;
                                final nedE = (fx - 0.5) * _MapPainter.kNedSpan;
                                final nedN = (0.5 - fy) * _MapPainter.kNedSpan;
                                ref.read(cursorNedProvider.notifier).state =
                                    NedGoal(nedN, nedE);
                              },
                              onExit: (_) => ref
                                  .read(cursorNedProvider.notifier)
                                  .state = null,
                              child: Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  Positioned(
                                    left: m,
                                    top: m,
                                    width: size.width,
                                    height: size.height,
                                    child: CustomPaint(
                                      painter: _MapPainter(
                                        goalNorth: pendingGoal?.north,
                                        goalEast: pendingGoal?.east,
                                        layer: widget.layer,
                                        liveTrail: liveTrail,
                                        liveHeadingDeg: headingDeg,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        }),
                      ),
                    ),
                  ),
                  // Static (non-zooming) overlays
                  const Positioned(
                    top: 8,
                    left: 8,
                    child: _CoordReadout(),
                  ),
                  const Positioned(
                    top: 8,
                    right: 8,
                    child: _CompassRose(),
                  ),
                  const Positioned(
                    bottom: 10,
                    left: 10,
                    child: _ScaleBar(),
                  ),
                  const Positioned(
                    bottom: 10,
                    right: 10,
                    child: _MapLegend(),
                  ),
                  // Bottom HUD telemetry strip
                  Positioned(
                    bottom: 38,
                    left: 0,
                    right: 0,
                    child: Center(child: _MapHud()),
                  ),
                  // AirSim offline banner (top-center, red, dismissible
                  // by simply launching AirSim).
                  if (!live)
                    const Positioned(
                      top: 10,
                      left: 0,
                      right: 0,
                      child: Center(child: _AirsimOfflineBanner()),
                    ),
                ],
              );
            },
          );
        }),
      ),
    );
  }
}

// ============================================================
// Map painter — vector cartography
// ============================================================
class _MapPainter extends CustomPainter {
  final String layer;

  /// Real flight trail in NED meters (north, east). Empty when AirSim is not
  /// streaming — the painter then falls back to its synthetic demo trail so
  /// the cartography view still looks alive.
  final List<TrailPoint> liveTrail;

  /// Heading in degrees from the latest telemetry frame (null when offline).
  final double? liveHeadingDeg;

  /// Pending goal in NED meters (north, east). When non-null the painter
  /// draws a persistent reticle at the projected position so the user can
  /// see exactly where the drone is heading.
  final double? goalNorth;
  final double? goalEast;

  _MapPainter({
    required this.layer,
    this.goalNorth,
    this.goalEast,
    this.liveTrail = const [],
    this.liveHeadingDeg,
  });

  /// Map display spans ±[kNedSpan/2] m in N/E around origin. MUST equal
  /// `_SimWorldMapState._nedSpanMeters` so the tap-to-NED inverse and the
  /// painter's NED-to-pixel use the same scale and the goal reticle lands
  /// exactly under the cursor.
  static const double kNedSpan = 100.0;

  /// Project an NED point (meters north, meters east) into widget-local
  /// pixel coordinates using a FIXED ±50 m window centred on the origin.
  /// This is the single source of truth for the map's coordinate frame.
  static Offset _projectNed(double north, double east, Size size) {
    final nx = 0.5 + east / kNedSpan;
    final ny = 0.5 - north / kNedSpan;
    return Offset(nx * size.width, ny * size.height);
  }

  @override
  void paint(Canvas canvas, Size size) {
    // 1. Base
    canvas.drawRect(Offset.zero & size, Paint()..color = AppColors.mapBg);

    // 2. Square grid + UTM ticks (only chrome we keep — gives spatial reference)
    _drawSquareGrid(canvas, size);

    // 3. Live flight trail (real NED) → drone glyph at the latest point.
    //    All synthetic cartography (hex grid, contours, water, roads,
    //    buildings, AOI, fake waypoints, demo trail) has been removed
    //    so the canvas is a clean grid showing only the live drone.
    Offset droneAt;
    double droneHeading;
    if (liveTrail.length >= 2) {
      final pts = _projectLiveTrail(liveTrail, size);
      final livePath = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (int i = 1; i < pts.length; i++) {
        livePath.lineTo(pts[i].dx, pts[i].dy);
      }
      canvas.drawPath(
        livePath,
        Paint()
          ..color = AppColors.accent.withOpacity(0.18)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 4.0
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
      canvas.drawPath(
        livePath,
        Paint()
          ..color = AppColors.accent
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.6
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round,
      );
      droneAt = pts.last;
      droneHeading = liveHeadingDeg ?? 0;
    } else if (liveTrail.length == 1) {
      final pts = _projectLiveTrail(liveTrail, size);
      droneAt = pts.first;
      droneHeading = liveHeadingDeg ?? 0;
    } else {
      // No live data — park the glyph at the NED origin (map centre) so the
      // canvas isn't empty and so its position matches a tap at NED (0,0).
      droneAt = _projectNed(0, 0, size);
      droneHeading = liveHeadingDeg ?? 0;
    }

    // 4. Persistent goal reticle. Drawn from NED so it stays geographically
    //    fixed even when the drone moves under it.
    if (goalNorth != null && goalEast != null) {
      _drawTargetReticle(
        canvas,
        _projectNed(goalNorth!, goalEast!, size),
        label: 'GOAL',
      );
    }

    // 5. Drone glyph
    _drawDrone(canvas, droneAt, headingDeg: droneHeading);

    // 6. Edge ticks / coordinate ruler
    _drawEdgeTicks(canvas, size);
  }

  // ---- helpers ----

  void _drawSquareGrid(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.mapGrid
      ..strokeWidth = 0.5;
    // The InteractiveViewer's boundaryMargin lets the user pan well beyond
    // the painter's `size` rect when zoomed out. We extend the grid the same
    // distance in every direction so the canvas never shows a hard edge —
    // wherever the operator drops a goal pin, they still see grid context.
    const cells = 10;
    final stepX = size.width / cells;
    final stepY = size.height / cells;
    const margin =
        2200.0; // matches InteractiveViewer boundaryMargin (2000) + slack
    final extraX = (margin / stepX).ceil();
    final extraY = (margin / stepY).ceil();
    final iMin = -extraX;
    final iMax = cells + extraX;
    final jMin = -extraY;
    final jMax = cells + extraY;
    final left = iMin * stepX;
    final right = iMax * stepX;
    final top = jMin * stepY;
    final bottom = jMax * stepY;

    final majorPaint = Paint()
      ..color = AppColors.mapGrid.withOpacity(0.55)
      ..strokeWidth = 0.7;

    for (int i = iMin; i <= iMax; i++) {
      final x = i * stepX;
      // Fade lines outside the central canvas slightly so the original 10x10
      // grid remains the visual anchor.
      final inside = i >= 0 && i <= cells;
      final p = inside
          ? ((i % 5 == 0) ? majorPaint : paint)
          : (Paint()
            ..color = AppColors.mapGrid.withOpacity(0.18)
            ..strokeWidth = 0.4);
      canvas.drawLine(Offset(x, top), Offset(x, bottom), p);
    }
    for (int j = jMin; j <= jMax; j++) {
      final y = j * stepY;
      final inside = j >= 0 && j <= cells;
      final p = inside
          ? ((j % 5 == 0) ? majorPaint : paint)
          : (Paint()
            ..color = AppColors.mapGrid.withOpacity(0.18)
            ..strokeWidth = 0.4);
      canvas.drawLine(Offset(left, y), Offset(right, y), p);
    }
  }

  void _drawEdgeTicks(Canvas canvas, Size size) {
    final tick = Paint()
      ..color = AppColors.mapTick
      ..strokeWidth = 0.8;
    const labelStyle = TextStyle(
      color: AppColors.mapTick,
      fontSize: 8.5,
      letterSpacing: 0.6,
      fontFamilyFallback: ['Consolas', 'monospace'],
    );
    // top: longitude
    for (int i = 1; i < 8; i++) {
      final x = size.width * i / 8;
      canvas.drawLine(Offset(x, 0), Offset(x, 5), tick);
      final tp = TextPainter(
        text: TextSpan(
          text: '122°${(8 - i).toString().padLeft(2, '0')}\'',
          style: labelStyle,
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(x + 2, 6));
    }
    // right: latitude
    for (int i = 1; i < 8; i++) {
      final y = size.height * i / 8;
      canvas.drawLine(Offset(size.width - 5, y), Offset(size.width, y), tick);
      final tp = TextPainter(
        text: TextSpan(
          text: '47°${(48 - i).toString().padLeft(2, '0')}\'',
          style: labelStyle,
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(size.width - tp.width - 6, y + 2));
    }
  }

  void _drawTargetReticle(Canvas canvas, Offset p, {required String label}) {
    final stroke = Paint()
      ..color = AppColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6;
    canvas.drawCircle(p, 16, stroke);
    canvas.drawCircle(p, 6, stroke);
    canvas.drawLine(p + const Offset(-22, 0), p + const Offset(-9, 0), stroke);
    canvas.drawLine(p + const Offset(9, 0), p + const Offset(22, 0), stroke);
    canvas.drawLine(p + const Offset(0, -22), p + const Offset(0, -9), stroke);
    canvas.drawLine(p + const Offset(0, 9), p + const Offset(0, 22), stroke);

    final tp = TextPainter(
      text: TextSpan(
        text: label,
        style: const TextStyle(
          color: AppColors.accent,
          fontSize: 9,
          letterSpacing: 1.4,
          fontWeight: FontWeight.w700,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(p.dx + 14, p.dy - tp.height / 2));
  }

  void _drawDrone(Canvas canvas, Offset p, {required double headingDeg}) {
    final hRad = (headingDeg - 90) * math.pi / 180;

    // FOV cone (subtle)
    final cone = Path()
      ..moveTo(p.dx, p.dy)
      ..lineTo(
        p.dx + math.cos(hRad - math.pi / 6) * 70,
        p.dy + math.sin(hRad - math.pi / 6) * 70,
      )
      ..arcToPoint(
        Offset(
          p.dx + math.cos(hRad + math.pi / 6) * 70,
          p.dy + math.sin(hRad + math.pi / 6) * 70,
        ),
        radius: const Radius.circular(70),
      )
      ..close();
    canvas.drawPath(
      cone,
      Paint()..color = AppColors.accent.withOpacity(0.08),
    );
    canvas.drawPath(
      cone,
      Paint()
        ..color = AppColors.accent.withOpacity(0.35)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.8,
    );

    // Heading tick (short line from rim of body in facing direction)
    canvas.drawLine(
      p + Offset(math.cos(hRad) * 6, math.sin(hRad) * 6),
      p + Offset(math.cos(hRad) * 18, math.sin(hRad) * 18),
      Paint()
        ..color = AppColors.accent
        ..strokeWidth = 1.6
        ..strokeCap = StrokeCap.round,
    );

    // Drone body — clean filled disc with halo + outline. No triangle.
    canvas.drawCircle(
      p,
      9,
      Paint()..color = AppColors.accent.withOpacity(0.18),
    );
    canvas.drawCircle(
      p,
      5.5,
      Paint()..color = AppColors.accent,
    );
    canvas.drawCircle(
      p,
      5.5,
      Paint()
        ..color = AppColors.mapBg
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );

    // Range rings around drone
    final ring = Paint()
      ..color = AppColors.text.withOpacity(0.18)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.6;
    canvas.drawCircle(p, 24, ring);
    canvas.drawCircle(p, 48, ring);

    // Callsign label
    final tp = TextPainter(
      text: const TextSpan(
        text: 'AS-4712',
        style: TextStyle(
          color: AppColors.text,
          fontSize: 8.5,
          letterSpacing: 1.2,
          fontWeight: FontWeight.w600,
          fontFamilyFallback: ['Consolas', 'monospace'],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, p + const Offset(10, 6));
  }

  @override
  bool shouldRepaint(covariant _MapPainter old) =>
      old.layer != layer ||
      old.goalNorth != goalNorth ||
      old.goalEast != goalEast ||
      !identical(old.liveTrail, liveTrail) ||
      old.liveHeadingDeg != liveHeadingDeg;

  /// Project an NED trail (north, east in metres) into widget-local pixel
  /// coordinates using the FIXED ±50 m window. The drone moves on a stable
  /// grid: the goal reticle stays put, the drone glyph drifts toward it,
  /// and pinch-zoom continues to work because [InteractiveViewer] handles
  /// the visual scale on top.
  List<Offset> _projectLiveTrail(List<TrailPoint> pts, Size size) {
    final out = <Offset>[];
    for (final p in pts) {
      out.add(_projectNed(p.north, p.east, size));
    }
    return out;
  }
}

// ============================================================
// Static overlays
// ============================================================
class _CoordReadout extends ConsumerWidget {
  const _CoordReadout();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = ref.watch(cursorNedProvider);
    final txt = c == null
        ? 'CURSOR  --'
        : 'N=${c.north.toStringAsFixed(1)} m  E=${c.east.toStringAsFixed(1)} m';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.mapBg.withOpacity(0.85),
        border: Border.all(color: AppColors.line2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('CURSOR',
              style: TextStyle(
                color: AppColors.textMute,
                fontSize: 8.5,
                letterSpacing: 1.4,
                fontWeight: FontWeight.w500,
              )),
          const SizedBox(width: 8),
          Text(txt,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 9.5,
                letterSpacing: 0.4,
                fontWeight: FontWeight.w500,
                fontFamilyFallback: ['Consolas', 'monospace'],
              )),
        ],
      ),
    );
  }
}

class _CompassRose extends StatelessWidget {
  const _CompassRose();
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 44,
      height: 44,
      child: CustomPaint(painter: _CompassPainter()),
    );
  }
}

class _CompassPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final r = size.width / 2 - 2;
    final ring = Paint()
      ..color = AppColors.lineStrong
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.8;
    canvas.drawCircle(c, r, ring);

    // N-S arrow
    final n = Path()
      ..moveTo(c.dx, c.dy - r + 2)
      ..lineTo(c.dx - 4, c.dy)
      ..lineTo(c.dx + 4, c.dy)
      ..close();
    canvas.drawPath(n, Paint()..color = AppColors.accent);
    final s = Path()
      ..moveTo(c.dx, c.dy + r - 2)
      ..lineTo(c.dx - 4, c.dy)
      ..lineTo(c.dx + 4, c.dy)
      ..close();
    canvas.drawPath(s, Paint()..color = AppColors.textMute);

    // N label
    final tp = TextPainter(
      text: const TextSpan(
        text: 'N',
        style: TextStyle(
          color: AppColors.text,
          fontSize: 9,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(c.dx - tp.width / 2, c.dy - r - 2));
  }

  @override
  bool shouldRepaint(covariant _CompassPainter old) => false;
}

class _ScaleBar extends StatelessWidget {
  const _ScaleBar();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.mapBg.withOpacity(0.85),
        border: Border.all(color: AppColors.line2),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            height: 7,
            child: CustomPaint(painter: _ScaleBarPainter()),
          ),
          const SizedBox(height: 3),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: const [
              Text('0',
                  style: TextStyle(
                      color: AppColors.textMute,
                      fontSize: 8.5,
                      fontFamilyFallback: ['Consolas', 'monospace'])),
              SizedBox(width: 36),
              Text('25',
                  style: TextStyle(
                      color: AppColors.textMute,
                      fontSize: 8.5,
                      fontFamilyFallback: ['Consolas', 'monospace'])),
              SizedBox(width: 30),
              Text('50 m',
                  style: TextStyle(
                      color: AppColors.textMute,
                      fontSize: 8.5,
                      fontFamilyFallback: ['Consolas', 'monospace'])),
            ],
          ),
        ],
      ),
    );
  }
}

class _ScaleBarPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = AppColors.text
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.8;
    final fill = Paint()..color = AppColors.text;
    canvas.drawRect(Offset.zero & size, stroke);
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width / 2, size.height), fill);
  }

  @override
  bool shouldRepaint(covariant _ScaleBarPainter old) => false;
}

class _MapLegend extends StatelessWidget {
  const _MapLegend();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.mapBg.withOpacity(0.85),
        border: Border.all(color: AppColors.line2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: const [
          _LegendRow(color: AppColors.text, label: 'DRONE'),
          SizedBox(height: 3),
          _LegendRow(color: AppColors.accent, label: 'GOAL'),
          SizedBox(height: 3),
          _LegendRow(color: AppColors.textDim, label: 'TRAIL'),
        ],
      ),
    );
  }
}

class _LegendRow extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendRow({required this.color, required this.label});
  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 2, color: color),
        const SizedBox(width: 6),
        Text(label,
            style: const TextStyle(
              color: AppColors.textDim,
              fontSize: 8.5,
              letterSpacing: 1.2,
              fontWeight: FontWeight.w500,
            )),
      ],
    );
  }
}

class _AirsimOfflineBanner extends ConsumerStatefulWidget {
  const _AirsimOfflineBanner();
  @override
  ConsumerState<_AirsimOfflineBanner> createState() =>
      _AirsimOfflineBannerState();
}

class _AirsimOfflineBannerState extends ConsumerState<_AirsimOfflineBanner> {
  bool _busy = false;

  Future<void> _retry() async {
    if (_busy) return;
    setState(() => _busy = true);
    final repo = ref.read(bridgeRepositoryProvider);
    await repo.startBridge();
    // Status will refresh on the next 3s poll; just clear the spinner.
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: _retry,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: AppColors.alert.withOpacity(0.18),
            border: Border.all(color: AppColors.alert, width: 1.0),
            borderRadius: BorderRadius.circular(2),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const StatusDot(color: AppColors.alert, size: 6),
              const SizedBox(width: 8),
              const Text(
                'AIRSIM OFFLINE',
                style: TextStyle(
                  color: AppColors.alert,
                  fontSize: 11,
                  letterSpacing: 2.0,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(width: 10),
              const Text(
                'WAITING FOR SIMULATION\u2026',
                style: TextStyle(
                  color: AppColors.textDim,
                  fontSize: 9.5,
                  letterSpacing: 1.4,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(width: 14),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  border: Border.all(
                      color: AppColors.alert.withOpacity(0.7), width: 0.8),
                  borderRadius: BorderRadius.circular(2),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_busy)
                      const SizedBox(
                        width: 9,
                        height: 9,
                        child: CircularProgressIndicator(
                          strokeWidth: 1.2,
                          valueColor:
                              AlwaysStoppedAnimation<Color>(AppColors.alert),
                        ),
                      )
                    else
                      const Icon(Icons.refresh,
                          size: 10, color: AppColors.alert),
                    const SizedBox(width: 5),
                    Text(
                      _busy ? 'STARTING\u2026' : 'RETRY',
                      style: const TextStyle(
                        color: AppColors.alert,
                        fontSize: 9.5,
                        letterSpacing: 1.4,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MapHud extends ConsumerWidget {
  const _MapHud();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final telemetryListenable = ref.watch(liveTelemetryProvider);
    return ValueListenableBuilder<Telemetry?>(
      valueListenable: telemetryListenable,
      builder: (context, t, _) {
        // Ms-precision readouts. SPD shows 3 decimals (mm/s), ALT 3 decimals (mm),
        // VS (vertical speed) 3 decimals so micro-movements during nav are visible.
        final spd = t == null ? '0.000' : t.groundSpeed.toStringAsFixed(3);
        final alt = t == null ? '0.000' : t.altitude.toStringAsFixed(3);
        final hdg =
            t == null ? '---' : t.headingDeg.toStringAsFixed(1).padLeft(5, '0');
        final vs = t == null ? '0.000' : (-t.velocityZ).toStringAsFixed(3);
        final ts = t?.timestamp != null
            ? '${t!.timestamp!.minute.toString().padLeft(2, '0')}:${t.timestamp!.second.toString().padLeft(2, '0')}.${t.timestamp!.millisecond.toString().padLeft(3, '0')}'
            : '--:--.---';
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: AppColors.mapBg.withOpacity(0.9),
            border: Border.all(color: AppColors.line2),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _HudCell(k: 'SPD', v: '$spd m/s'),
              const _HudSep(),
              _HudCell(k: 'ALT', v: '$alt m'),
              const _HudSep(),
              _HudCell(k: 'V/S', v: '$vs m/s'),
              const _HudSep(),
              _HudCell(k: 'HDG', v: '$hdg°'),
              const _HudSep(),
              _HudCell(k: 'T', v: ts),
            ],
          ),
        );
      },
    );
  }
}

class _HudCell extends StatelessWidget {
  final String k;
  final String v;
  const _HudCell({required this.k, required this.v});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Text(k,
              style: const TextStyle(
                color: AppColors.textMute,
                fontSize: 8.5,
                letterSpacing: 1.4,
                fontWeight: FontWeight.w500,
              )),
          const SizedBox(width: 6),
          Text(v,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
                fontFamilyFallback: ['Consolas', 'monospace'],
              )),
        ],
      ),
    );
  }
}

class _HudSep extends StatelessWidget {
  const _HudSep();
  @override
  Widget build(BuildContext context) =>
      Container(width: 1, height: 14, color: AppColors.line);
}

// ============================================================
// Right side panel
// ============================================================
class _RightPanel extends ConsumerStatefulWidget {
  const _RightPanel();
  @override
  ConsumerState<_RightPanel> createState() => _RightPanelState();
}

class _RightPanelState extends ConsumerState<_RightPanel> {
  bool _navPending = false;
  bool _landPending = false;

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: const TextStyle(fontSize: 12)),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
      ),
    );
    final upper = msg.toUpperCase();
    final level = upper.contains('FAIL') ||
            upper.contains('ERROR') ||
            upper.contains('REJECT')
        ? NoticeLevel.error
        : (upper.contains('DISPATCHED') || upper.contains('STARTED'))
            ? NoticeLevel.success
            : NoticeLevel.info;
    ref.read(notificationCenterProvider).push(level, 'Command', body: msg);
  }

  Future<void> _startNav() async {
    if (_navPending) return;
    final goal = ref.read(pendingGoalProvider);
    if (goal == null) {
      _toast('Tap the map to set a goal first');
      return;
    }
    final droneId = ref.read(selectedDroneIdProvider) ??
        ref.read(selectedDroneProvider)?.id;
    if (droneId == null) {
      _toast('No drone selected');
      return;
    }
    setState(() => _navPending = true);
    try {
      final ok = await ref.read(bridgeRepositoryProvider).startNavGoal(
            droneId: droneId,
            goalX: goal.north,
            goalY: goal.east,
          );
      _toast(ok
          ? 'NAV STARTED → N=${goal.north.toStringAsFixed(1)} E=${goal.east.toStringAsFixed(1)}'
          : 'Backend rejected NAV start');
    } catch (e) {
      _toast('NAV start failed: $e');
    } finally {
      if (mounted) setState(() => _navPending = false);
    }
  }

  Future<void> _emergencyLand({required String label}) async {
    if (_landPending) return;
    final droneId = ref.read(selectedDroneIdProvider) ??
        ref.read(selectedDroneProvider)?.id;
    if (droneId == null) {
      _toast('No drone selected');
      return;
    }
    setState(() => _landPending = true);
    try {
      final ok =
          await ref.read(bridgeRepositoryProvider).emergencyLand(droneId);
      if (ok) {
        // Clear any pending goal pin — emergency overrides operator intent.
        ref.read(pendingGoalProvider.notifier).state = null;
      }
      _toast(ok ? '$label DISPATCHED' : '$label FAILED');
    } catch (e) {
      _toast('$label error: $e');
    } finally {
      if (mounted) setState(() => _landPending = false);
    }
  }

  /// Return-To-Base: dispatch a NAV goal of (0, 0) — the drone's spawn /
  /// home position — and clear the operator's pending goal. This is a
  /// normal autonomous nav (uses A*+PPO), NOT an emergency abort.
  Future<void> _returnToBase() async {
    if (_navPending) return;
    final droneId = ref.read(selectedDroneIdProvider) ??
        ref.read(selectedDroneProvider)?.id;
    if (droneId == null) {
      _toast('No drone selected');
      return;
    }
    setState(() => _navPending = true);
    try {
      final ok = await ref.read(bridgeRepositoryProvider).startNavGoal(
            droneId: droneId,
            goalX: 0.0,
            goalY: 0.0,
          );
      if (ok) {
        ref.read(pendingGoalProvider.notifier).state = const NedGoal(0, 0);
      }
      _toast(ok ? 'RTB DISPATCHED → home (0, 0)' : 'RTB FAILED');
    } catch (e) {
      _toast('RTB error: $e');
    } finally {
      if (mounted) setState(() => _navPending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final goal = ref.watch(pendingGoalProvider);
    final goalLabel = goal == null
        ? 'TAP MAP TO SET'
        : 'N=${goal.north.toStringAsFixed(1)} E=${goal.east.toStringAsFixed(1)}';
    return Container(
      width: 220,
      decoration: const BoxDecoration(
        color: AppColors.panel,
        border: Border(left: BorderSide(color: AppColors.line)),
      ),
      padding: const EdgeInsets.all(12),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const _Section(title: 'NAV PLANNER'),
            const SizedBox(height: 10),
            _Kv(k: 'GOAL', v: goalLabel),
            const _Kv(k: 'DISTANCE', v: '--'),
            const _Kv(k: 'PATH LEN', v: '--'),
            const SizedBox(height: 6),
            const _Hr(),
            const SizedBox(height: 6),
            const _Kv(k: 'REPLANS', v: '--'),
            const _Kv(k: 'STUCK', v: '--'),
            const _Kv(k: 'PROACTIVE', v: '--'),
            const SizedBox(height: 18),
            const _Section(title: 'ENVIRONMENT'),
            const SizedBox(height: 10),
            const _Kv(k: 'CLOSEST OBS', v: '--'),
            const _Kv(k: 'MAPPED CELLS', v: '--'),
            const _Kv(k: 'WIND', v: '--'),
            const SizedBox(height: 18),
            const _Section(title: 'ACTIONS'),
            const SizedBox(height: 10),
            GhostButton(
              label: _navPending ? 'STARTING…' : 'START NAV',
              wide: true,
              icon: Icons.play_arrow_rounded,
              accentColor: AppColors.accent,
              onPressed: _navPending ? null : _startNav,
            ),
            const SizedBox(height: 8),
            GhostButton(
              label: _landPending ? 'WORKING…' : 'RTB',
              wide: true,
              icon: Icons.home_outlined,
              onPressed: (_navPending || _landPending) ? null : _returnToBase,
            ),
            const SizedBox(height: 8),
            GhostButton(
              label: _landPending ? 'WORKING…' : 'EMERGENCY',
              wide: true,
              icon: Icons.warning_amber_outlined,
              accentColor: AppColors.alert,
              onPressed: _landPending
                  ? null
                  : () => _emergencyLand(label: 'EMERGENCY LAND'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  const _Section({required this.title});
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(title, style: AppText.cardTitle),
        const SizedBox(width: 8),
        Expanded(child: Container(height: 1, color: AppColors.line)),
      ],
    );
  }
}

class _Hr extends StatelessWidget {
  const _Hr();
  @override
  Widget build(BuildContext context) =>
      Container(height: 1, color: AppColors.line);
}

class _Kv extends StatelessWidget {
  final String k;
  final String v;
  const _Kv({required this.k, required this.v});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k,
              style: const TextStyle(
                color: AppColors.textMute,
                fontSize: 9.5,
                letterSpacing: 1.4,
                fontWeight: FontWeight.w500,
              )),
          Text(v, style: AppText.dataSmall),
        ],
      ),
    );
  }
}

class _Bar extends StatelessWidget {
  final double percent;
  final Color color;
  const _Bar({required this.percent, required this.color});
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 4,
      child: Stack(
        children: [
          Container(color: AppColors.panel3),
          FractionallySizedBox(
            alignment: Alignment.centerLeft,
            widthFactor: percent,
            child: Container(color: color),
          ),
        ],
      ),
    );
  }
}
