#!/usr/bin/env python3
"""
nav_worker.py — Isolated NavRL navigation subprocess.

Runs in a completely separate Python process so the msgpackrpc tornado IOLoop
is private to this process. This prevents interference between the main
AirSim Auto-Bridge's connection and the planner's connection.

Usage:
    python nav_worker.py <goal_x> <goal_y> <base_alt>
                         <backend_url> <ws_url>
                         <drone_id> <auth_user> <auth_pass>

Exit codes:
    0 — navigation completed successfully
    1 — navigation failed or error
"""

import sys
import os
import logging
import numpy as np

# Force UTF-8 output so emoji in NavRLCityPlanner prints don't crash on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure the same directory is on the path so local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Argument parsing ─────────────────────────────────────────
if len(sys.argv) < 9:
    print(
        "Usage: nav_worker.py goal_x goal_y base_alt "
        "backend_url ws_url drone_id auth_user auth_pass",
        file=sys.stderr,
    )
    sys.exit(1)

goal_x    = float(sys.argv[1])
goal_y    = float(sys.argv[2])
base_alt  = float(sys.argv[3])
BACKEND_URL = sys.argv[4]
WS_URL      = sys.argv[5]
DRONE_ID    = sys.argv[6]
AUTH_USER   = sys.argv[7]
AUTH_PASS   = sys.argv[8]

# ── Logging — write to stdout so parent bridge captures it via PIPE ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("nav_worker")

logger.info(
    "Nav worker started: goal=[%.1f, %.1f] alt=%.1f drone=%s",
    goal_x, goal_y, base_alt, DRONE_ID,
)

# ── Imports (heavy — after arg-parse so startup errors are clear) ──
from command_center_bridge import CommandCenterBridge, BridgeConfig
from navrl_city_planner import NavRLCityPlanner


def main() -> bool:
    """Run navigation. Returns True on success."""

    # Create a planner bridge for telemetry streaming + remote commands
    planner_bridge = None
    try:
        cfg = BridgeConfig(
            drone_id=DRONE_ID,
            auth_username=AUTH_USER,
            auth_password=AUTH_PASS,
            base_url=BACKEND_URL,
            ws_url=WS_URL,
            enable_gps=True,
        )
        planner_bridge = CommandCenterBridge(cfg)
        if planner_bridge.connect():
            planner_bridge.start_command_listener()
            logger.info("Planner bridge connected")
        else:
            logger.warning("Planner bridge connect failed — continuing without remote control")
            planner_bridge = None
    except Exception as e:
        logger.warning("Planner bridge error: %s — continuing without remote control", e)
        planner_bridge = None

    # Create city planner (loads AI model)
    try:
        planner = NavRLCityPlanner()
        if planner_bridge:
            planner.command_bridge = planner_bridge
    except Exception as e:
        logger.error("Failed to create NavRLCityPlanner: %s", e)
        _report_nav_complete(planner_bridge, False, {})
        return False

    # Run navigation
    goal = np.array([goal_x, goal_y])
    result = {}
    try:
        result = planner.navigate_to_goal(goal, timeout=300.0, min_altitude=base_alt)
        success = result.get("success", False)
        logger.info(
            "Navigation finished: success=%s time=%.1fs efficiency=%.1f%%",
            success,
            result.get("time", 0),
            result.get("efficiency", 0),
        )
    except Exception as e:
        logger.error("Navigation error: %s", e, exc_info=True)
        success = False
        result = {"success": False, "error": str(e)}

    # Report nav complete to backend
    _report_nav_complete(planner_bridge, success, result)

    # Clean up planner bridge
    if planner_bridge is not None:
        try:
            planner_bridge.disconnect()
        except Exception:
            pass

    return success


def _report_nav_complete(
    planner_bridge: "CommandCenterBridge | None",
    success: bool,
    result: dict,
) -> None:
    """POST nav-complete to the backend."""
    import requests  # available via the existing venv

    url = f"{BACKEND_URL}/navrl/drones/{DRONE_ID}/nav-complete"
    payload = {
        "success": success,
        "metrics": {
            "efficiency":      result.get("efficiency", 0),
            "replans":         result.get("replans", 0),
            "distanceToGoal":  result.get("closest_obstacle", 0),
            "time":            result.get("time", 0),
            "pathLength":      result.get("path_length", 0),
        },
    }

    # Prefer the authenticated session from planner_bridge so the JWT is valid
    session = getattr(planner_bridge, "_session", None) if planner_bridge else None
    try:
        if session is not None:
            resp = session.post(url, json=payload, timeout=10)
        else:
            # Fallback: fresh login then POST
            import requests as _req
            login_resp = _req.post(
                f"{BACKEND_URL}/auth/login",
                json={"username": AUTH_USER, "password": AUTH_PASS},
                timeout=10,
            )
            token = login_resp.json().get("data", {}).get("token", "")
            resp = _req.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        logger.info("Nav complete reported: HTTP %d", resp.status_code)
    except Exception as e:
        logger.warning("Nav complete report failed: %s", e)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
