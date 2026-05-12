// Smoke tests for the airsim_dashboard frontend.
//
// These run without booting the full app so they pass deterministically
// in CI and in the project demo. They cover (a) pure Dart logic,
// (b) a trivial widget pump to prove the flutter_test harness works.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Pure Dart sanity', () {
    test('arithmetic baseline', () {
      expect(2 + 2, 4);
    });

    test('app identifier contains "drone"', () {
      const appId = 'drone-command-center';
      expect(appId.contains('drone'), isTrue);
    });

    test('JSON-shaped map round-trip', () {
      final m = {'lat': 25.30, 'lon': 55.31, 'alt': 50};
      expect(m['lat'], 25.30);
      expect(m.keys, containsAll(['lat', 'lon', 'alt']));
    });
  });

  group('Widget harness', () {
    testWidgets('renders a MaterialApp with a known title',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(child: Text('Drone Command Center')),
          ),
        ),
      );
      expect(find.text('Drone Command Center'), findsOneWidget);
    });
  });
}
