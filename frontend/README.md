# AIRSIM Dashboard – Flutter

A Flutter port of the AIRSIM drone control dashboard design.

## Run

```bash
cd airsim_flutter
flutter pub get
flutter run -d windows   # or chrome / macos / linux
```

The dashboard is sized for a 1140×980 viewport and centers itself on a black backdrop.

## Structure

```
lib/
  main.dart
  ui/
    theme.dart                 # Colors + text styles
    dashboard_page.dart        # Top-level layout (sidebar + main area)
    widgets/
      panel_card.dart          # Reusable card / button / status dot
      sidebar.dart             # Left navigation rail
      topbar.dart              # Coordinates / heading / battery row
      left_column.dart         # Mission, control, subsystems, lidar
      sim_world_map.dart       # Center radar with NAV PLANNER, ENV, actions
      fpv_camera.dart          # Stylized live-video panel
      bead_metric.dart         # SPEED / ALTITUDE beaded progress
      footer.dart              # Status bar
```
