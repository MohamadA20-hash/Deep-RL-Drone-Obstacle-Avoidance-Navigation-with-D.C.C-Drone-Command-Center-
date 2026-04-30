import 'package:flutter/material.dart';
import 'dart:ui' show FontFeature;

/// Palantir / Anduril-inspired palette: near-monochrome slate with one
/// warm amber accent, used sparingly. No neon, no saturated blues.
class AppColors {
  // Surfaces — deep, cool, almost black
  static const bg = Color(0xFF06080B);
  static const sidebar = Color(0xFF080A0E);
  static const main = Color(0xFF0A0D12);
  static const panel = Color(0xFF0E1218);
  static const panel2 = Color(0xFF0B0F14);
  static const panel3 = Color(0xFF131820);

  // Hairlines
  static const line = Color(0xFF1A2230);
  static const line2 = Color(0xFF232C3B);
  static const lineStrong = Color(0xFF2C3848);

  // Text — cool slate scale
  static const text = Color(0xFFD6DCE3);
  static const textDim = Color(0xFF8794A2);
  static const textMute = Color(0xFF5A6573);
  static const label = Color(0xFF6B7785);

  // Accent — single warm amber, used very sparingly
  static const accent = Color(0xFFC9A063);
  static const accentDim = Color(0xFF8A6D40);
  static const accentSoft = Color(0xFF3A2E1B);

  // Status — desaturated, only when meaning matters
  static const ok = Color(0xFF6FB58A);
  static const warn = Color(0xFFD49A4A);
  static const alert = Color(0xFFC75450);

  // Map cartography
  static const mapBg = Color(0xFF0A0E14);
  static const mapTerrain = Color(0xFF11161E);
  static const mapWater = Color(0xFF0E1A26);
  static const mapBuilding = Color(0xFF1A2230);
  static const mapBuildingEdge = Color(0xFF2A3548);
  static const mapRoad = Color(0xFF2A3140);
  static const mapContour = Color(0xFF1C2632);
  static const mapGrid = Color(0xFF141B26);
  static const mapTick = Color(0xFF4A5564);
}

class AppTheme {
  static ThemeData get dark => ThemeData(
        useMaterial3: false,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: AppColors.bg,
        fontFamily: 'Inter',
        colorScheme: const ColorScheme.dark(
          primary: AppColors.accent,
          surface: AppColors.panel,
        ),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(color: AppColors.text),
        ),
      );
}

/// Reusable text styles. Two families:
///   - Geometric sans (default) for labels / chrome
///   - Tabular figures (mono) for telemetry / numeric data
class AppText {
  static const _mono = <String>['Consolas', 'SF Mono', 'Menlo', 'monospace'];
  static const _tabular = [FontFeature.tabularFigures()];

  // Tiny uppercase labels — Palantir signature
  static const label = TextStyle(
    fontSize: 9.5,
    letterSpacing: 1.6,
    color: AppColors.label,
    fontWeight: FontWeight.w500,
  );
  static const labelDim = TextStyle(
    fontSize: 9.5,
    letterSpacing: 1.6,
    color: AppColors.textMute,
    fontWeight: FontWeight.w500,
  );
  static const cardTitle = TextStyle(
    fontSize: 10.5,
    letterSpacing: 2.0,
    color: AppColors.text,
    fontWeight: FontWeight.w600,
  );
  static const cardSub = TextStyle(
    fontSize: 10.5,
    color: AppColors.textMute,
    letterSpacing: 0.2,
    fontWeight: FontWeight.w400,
  );

  // Numeric / telemetry — tabular figures
  static const value = TextStyle(
    fontSize: 13,
    color: AppColors.text,
    fontWeight: FontWeight.w500,
    fontFamilyFallback: _mono,
    fontFeatures: _tabular,
  );
  static const valueLarge = TextStyle(
    fontSize: 22,
    color: Colors.white,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.2,
    fontFamilyFallback: _mono,
    fontFeatures: _tabular,
  );
  static const dataSmall = TextStyle(
    fontSize: 11,
    color: AppColors.text,
    fontWeight: FontWeight.w500,
    fontFamilyFallback: _mono,
    fontFeatures: _tabular,
  );

  static const navLabel = TextStyle(
    fontSize: 10,
    letterSpacing: 1.8,
    color: AppColors.textDim,
    fontWeight: FontWeight.w500,
  );
}
