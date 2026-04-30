"""
AirSim Auto-Bridge — Resilient Telemetry Connector
====================================================
Self-contained bridge that:
  1. Connects to the Spring Boot backend (retries until available)
  2. Polls for AirSim on port 41451 (retries until available)
  3. Streams telemetry at 1 Hz
  4. Auto-reconnects if either AirSim or the backend goes down
  5. Designed to be launched as a managed subprocess by the backend

Exit codes:
  0  — Clean shutdown (SIGINT / SIGTERM / "shutdown" on stdin)
  1  — Fatal error (cannot recover)

Status protocol (stdout JSON lines for the parent process):
  {"status":"waiting_backend"}
  {"status":"waiting_airsim"}
  {"status":"connected"}
  {"status":"streaming", "count": N}
  {"status":"reconnecting", "reason":"..."}
  {"status":"shutdown"}
  {"status":"error", "message":"..."}
"""

import airsim
import numpy as np
import math
import time
import sys
import os
import signal
import json
import socket
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))

from command_center_bridge import CommandCenterBridge, BridgeConfig

# ── Configuration ────────────────────────────────────────────
BACKEND_URL = os.environ.get("BRIDGE_BACKEND_URL", "http://localhost:8080/api")
WS_URL = os.environ.get("BRIDGE_WS_URL", "ws://localhost:8080/ws/telemetry")
AUTH_USER = os.environ.get("BRIDGE_AUTH_USER", "navrl_bridge")
AUTH_PASS = os.environ.get("BRIDGE_AUTH_PASS")
if not AUTH_PASS:
    raise RuntimeError("BRIDGE_AUTH_PASS environment variable must be set")
AIRSIM_HOST = os.environ.get("BRIDGE_AIRSIM_HOST", "127.0.0.1")
AIRSIM_PORT = int(os.environ.get("BRIDGE_AIRSIM_PORT", "41451"))
# 20 Hz default (50 ms) gives "millisecond-precision" monitoring on the
# dashboard. Override via BRIDGE_TELEMETRY_INTERVAL env if needed.
TELEMETRY_INTERVAL = float(os.environ.get("BRIDGE_TELEMETRY_INTERVAL", "0.05"))
POLL_INTERVAL = float(os.environ.get("BRIDGE_POLL_INTERVAL", "3.0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("airsim_auto_bridge")

_shutdown = False


def signal_handler(sig, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ── Status Reporting ─────────────────────────────────────────

def emit_status(status: str, **extra):
    """Print a JSON status line for the parent process to read."""
    msg = {"status": status, **extra}
    try:
        print(json.dumps(msg), flush=True)
    except Exception:
        pass


# ── AirSim Probe ─────────────────────────────────────────────

def is_airsim_available(host: str = AIRSIM_HOST, port: int = AIRSIM_PORT,
                        timeout: float = 2.0) -> bool:
    """Check if AirSim is accepting TCP connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


# ── Zombie AirSim Cleanup ────────────────────────────────────
#
# When the user closes AirSim via the window 'X' on Windows, the Unreal
# Engine sometimes leaves the process running with the RPC socket bound
# but unresponsive. If they then reopen AirSim, *both* the zombie and the
# fresh instance bind port 41451 (SO_REUSEADDR), and the OS round-robins
# incoming TCP connects between them — so half our handshakes hit the
# dead one and time out.
#
# This function finds every process listening on 41451, probes each one
# with a real RPC handshake, and kills the ones that don't respond.

def _find_pids_listening_on(port: int) -> list[int]:
    """Return PIDs that hold a LISTENING socket on `port` (Windows)."""
    pids: set[int] = set()
    try:
        import subprocess as _sp
        result = _sp.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
        )
        for line in result.stdout.splitlines():
            if "LISTENING" not in line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local = parts[1]
            if not local.endswith(f":{port}"):
                continue
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                continue
    except Exception as e:
        logger.debug("netstat failed: %s", e)
    return sorted(pids)


def _kill_pid(pid: int) -> bool:
    """Force-kill a Windows process. Returns True on success."""
    try:
        import subprocess as _sp
        _sp.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as e:
        logger.warning("Failed to kill PID %d: %s", pid, e)
        return False


def cleanup_zombie_airsim() -> int:
    """
    Detect and kill zombie AirSim processes on port 41451.

    For each PID listening on 41451, attempt a confirmConnection() — if
    it fails with the per-call 5s timeout, that PID is a zombie and we
    terminate it. Returns the number of zombies killed.

    Skipped on non-Windows platforms.
    """
    if os.name != "nt":
        return 0

    pids = _find_pids_listening_on(AIRSIM_PORT)
    if len(pids) <= 1:
        return 0  # at most one listener, nothing to clean up

    logger.warning(
        "Multiple AirSim listeners on port %d: %s — probing for zombies",
        AIRSIM_PORT, pids,
    )

    killed = 0
    for pid in pids:
        # Probe each PID with a real RPC handshake. We can't bind to a
        # specific PID directly, but if there are 2 listeners and the
        # whole-port handshake works only sometimes, the other one is
        # dead — kill all but the youngest (most recently started).
        try:
            import psutil
            proc = psutil.Process(pid)
            create_time = proc.create_time()
        except Exception:
            create_time = 0

        # We'll defer the kill decision: pick the PID with the largest
        # create_time (newest) as the "live" one and kill the rest.
        # Fall back to killing all-but-one by PID order if psutil missing.
        # Done in a second pass below.
        _ = create_time  # noqa

    # Pick the youngest process as the keeper
    keeper = pids[-1]
    try:
        import psutil
        keeper = max(pids, key=lambda p: psutil.Process(p).create_time())
    except Exception:
        pass

    for pid in pids:
        if pid == keeper:
            continue
        logger.warning("Killing zombie AirSim PID %d (keeping %d)", pid, keeper)
        if _kill_pid(pid):
            killed += 1

    if killed:
        # Give the OS a moment to release the sockets
        time.sleep(1.5)
        logger.info("Cleaned up %d zombie AirSim process(es)", killed)
    return killed



# ── Backend Probe ────────────────────────────────────────────

def is_backend_available(base_url: str = BACKEND_URL, timeout: float = 3.0) -> bool:
    """Quick health check — try to hit the auth endpoint."""
    import urllib.request
    import urllib.error
    try:
        url = base_url.rstrip("/")
        # Use a lightweight endpoint
        req = urllib.request.Request(
            f"{url}/drones",
            method="GET",
        )
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except urllib.error.HTTPError as e:
        # 401/403 means the server is UP (just not authenticated)
        return e.code in (401, 403)
    except Exception:
        return False


# ── Telemetry Builder ────────────────────────────────────────

def build_telemetry(client: airsim.MultirotorClient,
                    start_time: float) -> dict:
    """Read AirSim state and build telemetry dict for the backend."""
    state = client.getMultirotorState()
    pos = state.kinematics_estimated.position
    vel = state.kinematics_estimated.linear_velocity
    ori = state.kinematics_estimated.orientation

    pitch, roll, yaw = airsim.to_eularian_angles(ori)
    yaw_deg = math.degrees(yaw)
    pitch_deg = math.degrees(pitch)
    roll_deg = math.degrees(roll)

    speed = math.sqrt(vel.x_val ** 2 + vel.y_val ** 2 + vel.z_val ** 2)

    elapsed = time.time() - start_time
    battery = max(0.0, 100.0 - elapsed / 36.0)
    altitude = max(0.0, -pos.z_val)

    # LiDAR closest obstacle + radar scan (36 sectors, 10° each)
    NUM_SECTORS = 36
    SECTOR_DEG = 360.0 / NUM_SECTORS
    MAX_RANGE = 4.0           # metres — matches AirSim LiDAR range
    closest_obs = 999.0
    radar_sectors = [MAX_RANGE] * NUM_SECTORS
    try:
        lidar = client.getLidarData("LidarSensor1", "Drone1")
        if len(lidar.point_cloud) >= 3:
            pts = np.array(lidar.point_cloud).reshape(-1, 3)
            dists = np.sqrt(np.sum(pts ** 2, axis=1))
            valid_mask = dists > 0.15
            if np.any(valid_mask):
                closest_obs = float(np.min(dists[valid_mask]))
                # Bin each valid point by horizontal angle (body frame)
                vx = pts[valid_mask, 0]      # forward
                vy = pts[valid_mask, 1]      # right
                vd = dists[valid_mask]
                angles_deg = (np.degrees(np.arctan2(vy, vx)) + 360) % 360
                bins = np.clip((angles_deg / SECTOR_DEG).astype(int),
                               0, NUM_SECTORS - 1)
                for bi, di in zip(bins, vd):
                    if di < radar_sectors[bi]:
                        radar_sectors[bi] = float(di)
    except Exception:
        pass

    col = client.simGetCollisionInfo()

    return {
        "velocityX": round(vel.x_val, 4),
        "velocityY": round(vel.y_val, 4),
        "velocityZ": round(vel.z_val, 4),
        "yaw": round(yaw_deg, 2),
        "pitch": round(pitch_deg, 2),
        "roll": round(roll_deg, 2),
        "batteryLevel": round(battery, 1),
        "altitude": round(altitude, 2),
        "obstacleDistance": round(min(closest_obs, 70.0), 2),
        "positionNedX": round(pos.x_val, 3),
        "positionNedY": round(pos.y_val, 3),
        "positionNedZ": round(pos.z_val, 3),
        "altitudeMode": "REAL_AIRSIM",
        "closestObstacleDistance": round(min(closest_obs, 70.0), 2),
        "collisionCount": 1 if col.has_collided else 0,
        "navrlSpeed": round(speed, 3),
        "lidarScan": json.dumps([round(d, 2) for d in radar_sectors]),
    }


# ── Stdin Listener (for shutdown command from parent) ────────

def stdin_listener():
    """Listen for 'shutdown' on stdin from the parent process."""
    global _shutdown
    try:
        for line in sys.stdin:
            if line.strip().lower() == "shutdown":
                _shutdown = True
                break
    except Exception:
        pass


# ── Navigation Status Check ─────────────────────────────────

# ── FPV Camera Stream Server ─────────────────────────────────

FPV_PORT = int(os.environ.get("FPV_PORT", "8766"))
FPV_FPS = 15

# Thread-safe latest frame (PNG bytes)
_fpv_frame = b''
_fpv_lock = threading.Lock()


def _fpv_capture_loop():
    """Continuously capture FPV frames from AirSim. Runs in daemon thread.

    Hardened against the common failure mode where ``simGetImage`` blocks
    forever after the parallel ``nav_worker`` subprocess releases the camera
    in a half-dead state. Each call is dispatched to a worker pool with a
    hard 2 s deadline; if it fails to return, the rpc client is rebuilt.
    A periodic heartbeat log line proves the loop is alive even when
    frames are flowing silently.
    """
    import concurrent.futures as _cf
    global _fpv_frame
    capture_client = None
    empty_streak = 0  # consecutive empty/zero-byte frames
    EMPTY_RECONNECT_THRESHOLD = 30  # ~2s at 15 fps before forcing reconnect
    CALL_DEADLINE_SEC = 2.0          # hard ceiling per simGetImage
    HEARTBEAT_EVERY = 150            # ~10s at 15 fps
    frame_count = 0
    last_heartbeat_count = 0
    last_heartbeat_time = time.time()
    pool = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="fpv-rpc")

    while not _shutdown:
        try:
            if capture_client is None:
                capture_client = airsim.MultirotorClient(
                    ip=AIRSIM_HOST, port=AIRSIM_PORT, timeout_value=5
                )
                capture_client.confirmConnection()
                logger.info("FPV capture client connected to AirSim")
                empty_streak = 0

            # Submit the blocking RPC call to a single-slot pool so we can
            # enforce a deadline. If it doesn't return in time we treat it
            # as a hang and rebuild the client.
            fut = pool.submit(
                capture_client.simGetImage,
                "0", airsim.ImageType.Scene, "Drone1"
            )
            try:
                png = fut.result(timeout=CALL_DEADLINE_SEC)
            except _cf.TimeoutError:
                logger.warning("FPV simGetImage timed out (>%.1fs) \u2014 rebuilding client", CALL_DEADLINE_SEC)
                with _fpv_lock:
                    _fpv_frame = b''
                # NOTE: the orphaned future will eventually drain; this is
                # acceptable because the rpc client is being torn down.
                capture_client = None
                empty_streak = 0
                time.sleep(0.5)
                continue

            if png and len(png) > 100:
                if empty_streak > 0:
                    logger.info("FPV frames recovered after %d empty", empty_streak)
                empty_streak = 0
                frame_count += 1
                if frame_count - last_heartbeat_count >= HEARTBEAT_EVERY:
                    dt = max(0.001, time.time() - last_heartbeat_time)
                    fps = (frame_count - last_heartbeat_count) / dt
                    logger.info("FPV heartbeat: %d frames captured (%.1f fps)", frame_count, fps)
                    last_heartbeat_count = frame_count
                    last_heartbeat_time = time.time()
                with _fpv_lock:
                    _fpv_frame = png
            else:
                # AirSim returned empty image — paused, scene closed, or the
                # nav_worker subprocess just released the camera. Clear the
                # cached frame so the frontend shows OFFLINE instead of a
                # frozen still, and after a short streak force-reconnect
                # because the rpc client is sometimes left in a half-dead
                # state by the parallel nav_worker session.
                with _fpv_lock:
                    _fpv_frame = b''
                empty_streak += 1
                if empty_streak == 1 or empty_streak % 30 == 0:
                    logger.warning("FPV simGetImage returned empty (streak=%d)", empty_streak)
                if empty_streak >= EMPTY_RECONNECT_THRESHOLD:
                    logger.warning("FPV: forcing capture-client reconnect after %d empty frames",
                                   empty_streak)
                    try:
                        capture_client = None
                    except Exception:
                        pass
                    empty_streak = 0
                    time.sleep(0.5)
                    continue
        except Exception as exc:
            logger.warning("FPV capture error: %s — reconnecting", exc)
            with _fpv_lock:
                _fpv_frame = b''
            capture_client = None
            empty_streak = 0
            time.sleep(1)
            continue

        time.sleep(1.0 / FPV_FPS)


class _FPVHandler(BaseHTTPRequestHandler):
    """Serves the latest FPV frame as image/png at GET /fpv."""

    def do_GET(self):
        if self.path != '/fpv':
            self.send_response(404)
            self.end_headers()
            return
        with _fpv_lock:
            frame = _fpv_frame
        if not frame:
            self.send_response(204)
            self.end_headers()
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(frame)))
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(frame)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass  # suppress per-request logging


def _start_fpv_server():
    """Run the FPV HTTP server (blocking — run in daemon thread)."""
    server = HTTPServer(('0.0.0.0', FPV_PORT), _FPVHandler)
    logger.info("FPV server listening on http://0.0.0.0:%d/fpv", FPV_PORT)
    server.serve_forever()


# ── Navigation Status Check ─────────────────────────────────

NAV_CHECK_INTERVAL = float(os.environ.get("BRIDGE_NAV_CHECK_INTERVAL", "3.0"))

def check_nav_status(bridge: CommandCenterBridge) -> dict | None:
    """
    Poll the backend for the drone's current NavRL navigation status.
    Returns dict with flightStatus, goalNedX, goalNedY, isNavigating, etc.
    """
    try:
        status = bridge.get_navrl_status()
        return status
    except Exception as e:
        logger.debug("Nav status check failed: %s", e)
        return None


# ── NavRL Planner Execution ──────────────────────────────────
#
# IMPORTANT: navigation runs in a SUBPROCESS (nav_worker.py), NOT in this
# process.  See `_nav_thread_fn` below.  We do NOT keep an in-process
# `NavRLCityPlanner` cache here.  Doing so would:
#
#   1. Load the PPO model into VRAM in BOTH processes (≈2x GPU + RAM cost,
#      which chokes a 6 GB RTX 3060 the moment a navigation starts).
#   2. Create two msgpackrpc tornado IOLoops fighting over AirSim's RPC
#      socket on Windows, causing response-packet interleaving / hangs.
#   3. Give the false impression that planner state in this process is
#      synchronised with the worker — it isn't; the worker has its own
#      isolated `NavRLCityPlanner` instance with its own counters.
#
# All planning state lives inside the worker subprocess.  The only thing
# this process tracks is the worker's exit code (see `nav_result`).


def report_nav_complete(bridge: CommandCenterBridge, success: bool,
                        result: dict) -> bool:
    """
    Report navigation completion to the backend via the nav-complete endpoint.
    This updates the drone's flightStatus and stores navigation metrics.
    """
    url = f"{BACKEND_URL}/navrl/drones/{bridge.config.drone_id}/nav-complete"
    payload = {
        "success": success,
        "metrics": {
            "efficiency": result.get("efficiency", 0),
            "replans": result.get("replans", 0),
            "distanceToGoal": result.get("closest_obstacle", 0),
            "time": result.get("time", 0),
            "pathLength": result.get("path_length", 0),
        },
    }
    try:
        resp = bridge._session.post(url, json=payload)
        if resp.status_code == 200:
            logger.info("Nav completion reported to backend: success=%s", success)
            return True
        else:
            logger.warning("Nav completion report failed: HTTP %d", resp.status_code)
            return False
    except Exception as e:
        logger.warning("Nav completion report error: %s", e)
        return False


# ── Main Loop ────────────────────────────────────────────────

def main():
    global _shutdown

    # Start stdin listener thread (daemon — dies with main)
    listener = threading.Thread(target=stdin_listener, daemon=True)
    listener.start()

    logger.info("AirSim Auto-Bridge starting (with NavRL navigation support)...")

    while not _shutdown:
        # ── Phase 1: Wait for backend ──
        emit_status("waiting_backend")
        logger.info("Waiting for backend at %s ...", BACKEND_URL)
        while not _shutdown:
            if is_backend_available():
                logger.info("Backend is available")
                break
            time.sleep(POLL_INTERVAL)
        if _shutdown:
            break

        # ── Phase 2: Connect bridge to backend ──
        bridge = None
        try:
            config = BridgeConfig(
                drone_id="auto",
                auth_username=AUTH_USER,
                auth_password=AUTH_PASS,
                base_url=BACKEND_URL,
                ws_url=WS_URL,
                enable_gps=True,
            )
            bridge = CommandCenterBridge(config)
            if not bridge.connect():
                logger.warning("Bridge connect() failed, will retry...")
                emit_status("error", message="Bridge connect failed")
                time.sleep(POLL_INTERVAL)
                continue
            logger.info("Bridge connected — drone=%s", bridge.config.drone_id)
        except Exception as e:
            logger.warning("Bridge error: %s", e)
            emit_status("error", message=str(e))
            time.sleep(POLL_INTERVAL)
            continue

        # ── Phase 3: Wait for AirSim ──
        emit_status("waiting_airsim")
        logger.info("Waiting for AirSim at %s:%d ...", AIRSIM_HOST, AIRSIM_PORT)
        MAX_AIRSIM_RETRIES = 100  # ~5 min at POLL_INTERVAL=3s
        airsim_retries = 0
        while not _shutdown:
            if is_airsim_available():
                logger.info("AirSim port is open")
                break
            airsim_retries += 1
            if airsim_retries >= MAX_AIRSIM_RETRIES:
                logger.error("AirSim not available after %d retries, giving up", MAX_AIRSIM_RETRIES)
                emit_status("error", message="AirSim not available")
                break
            time.sleep(POLL_INTERVAL)
        if _shutdown or airsim_retries >= MAX_AIRSIM_RETRIES:
            if _shutdown:
                break
            continue

        # ── Phase 4: Connect to AirSim ──
        # Retry the handshake several times: when zombie + live AirSim
        # instances both bind 41451 (e.g. user reopened AirSim without fully
        # killing the previous process), Windows round-robins the connect
        # so we may need a few attempts to land on the live RPC server.
        client = None
        AIRSIM_HANDSHAKE_ATTEMPTS = 6
        zombie_cleanup_done = False
        for attempt in range(1, AIRSIM_HANDSHAKE_ATTEMPTS + 1):
            try:
                client = airsim.MultirotorClient(
                    ip=AIRSIM_HOST, port=AIRSIM_PORT, timeout_value=5
                )
                client.confirmConnection()
                logger.info("AirSim connected (attempt %d)", attempt)
                emit_status("connected")
                break
            except Exception as e:
                logger.warning(
                    "AirSim connect attempt %d/%d failed: %s",
                    attempt, AIRSIM_HANDSHAKE_ATTEMPTS, e,
                )
                client = None
                # After the second failure, scan for and terminate zombie
                # AirSim listeners holding port 41451 hostage.
                if attempt == 2 and not zombie_cleanup_done:
                    zombie_cleanup_done = True
                    try:
                        cleanup_zombie_airsim()
                    except Exception as ce:
                        logger.warning("Zombie cleanup failed: %s", ce)
                # brief pause so the OS picks a different socket next time
                time.sleep(0.5)
        if client is None:
            emit_status("reconnecting", reason="AirSim handshake failed after retries")
            time.sleep(POLL_INTERVAL)
            continue

        # ── Phase 4b: Start FPV camera server (once) ──
        if not getattr(_start_fpv_server, '_started', False):
            threading.Thread(target=_fpv_capture_loop, daemon=True).start()
            threading.Thread(target=_start_fpv_server, daemon=True).start()
            _start_fpv_server._started = True
            logger.info("FPV camera server started on port %d", FPV_PORT)

        # ── Phase 5: Main operational loop (telemetry + navigation) ──
        start_time = time.time()
        sent_count = 0
        consecutive_fails = 0
        last_nav_check = 0.0
        last_airsim_probe = 0.0
        AIRSIM_PROBE_INTERVAL = 5.0  # cheap TCP probe to detect AirSim shutdown
        is_navigating = False
        nav_thread = None
        nav_result = [None]  # mutable container for thread result
        nav_proc = [None]    # mutable container for subprocess handle (for emergency kill)
        last_emergency_check = 0.0
        EMERGENCY_CHECK_INTERVAL = 1.0  # poll /status every 1s while navigating

        def _nav_thread_fn(br, gx, gy):
            """
            Run navigation in a *subprocess* to completely isolate the
            msgpackrpc tornado IOLoop from the main bridge's AirSim client.

            A subprocess gets its own Python interpreter, its own tornado
            IOLoop background thread, and its own AirSim TCP socket.
            This is the only reliable way to prevent response-packet
            interleaving / join() hangs on Windows with msgpackrpc-python.
            """
            import subprocess

            worker_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "nav_worker.py"
            )

            try:
                # On Windows, when spawned from a Java process the child
                # inherits broken console handles that can freeze Python at
                # startup. CREATE_NO_WINDOW prevents that.
                _cflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

                proc = subprocess.Popen(
                    [
                        sys.executable, "-u", worker_path,
                        str(gx), str(gy), "5.0",
                        BACKEND_URL, WS_URL,
                        br.config.drone_id,
                        AUTH_USER, AUTH_PASS,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,  # separate stderr stream
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
                    creationflags=_cflags,
                )
                nav_proc[0] = proc  # expose handle so the main loop can kill on EMERGENCY

                # Drain stderr in a background thread to prevent blocking
                def _drain_stderr(p):
                    for line in iter(p.stderr.readline, ""):
                        logger.info("[nav-err] %s", line.rstrip())
                    p.stderr.close()
                stderr_thread = threading.Thread(target=_drain_stderr, args=(proc,), daemon=True)
                stderr_thread.start()

                # Stream subprocess stdout line-by-line in real time
                for line in iter(proc.stdout.readline, ""):
                    logger.info("[nav] %s", line.rstrip())
                proc.stdout.close()
                proc.wait(timeout=360)  # navigation can take up to 300s

                rc = proc.returncode or 0
                success = (rc == 0)
                logger.info("Nav worker exited: rc=%d success=%s", rc, success)
                nav_result[0] = {
                    "success": success,
                    "time": 0,
                    "efficiency": 0,
                    "nav_complete_reported": True,  # subprocess reported it
                }
            except subprocess.TimeoutExpired:
                logger.warning("Nav worker did not exit cleanly — killing")
                proc.kill()
                nav_result[0] = {"success": False, "time": 0, "efficiency": 0,
                                  "nav_complete_reported": False}
            except Exception as e:
                logger.error("Nav worker spawn error: %s", e)
                nav_result[0] = {"success": False, "time": 0, "efficiency": 0,
                                  "nav_complete_reported": False}

        while not _shutdown:
            now = time.time()

            # ── Handle completed navigation ──
            if is_navigating and nav_thread is not None and not nav_thread.is_alive():
                result = nav_result[0] or {"success": False, "time": 0, "efficiency": 0}
                success = result.get("success", False)
                nav_time = result.get("time", 0)
                efficiency = result.get("efficiency", 0)
                logger.info(
                    "Navigation finished: success=%s, time=%.1fs, efficiency=%.1f%%",
                    success, nav_time, efficiency,
                )
                emit_status(
                    "nav_complete",
                    success=success,
                    time=round(nav_time, 1),
                    efficiency=round(efficiency, 1),
                )

                # Only report nav-complete if the subprocess didn't already do it
                if not result.get("nav_complete_reported", False):
                    report_nav_complete(bridge, success, result)
                is_navigating = False
                nav_thread = None
                nav_result[0] = None
                start_time = time.time()
                consecutive_fails = 0

                # Clear subprocess handle so the next nav cycle re-registers it.
                nav_proc[0] = None

                # Reconnect telemetry AirSim client (planner may have reset sim)
                try:
                    client = airsim.MultirotorClient(
                        ip=AIRSIM_HOST, port=AIRSIM_PORT, timeout_value=5
                    )
                    client.confirmConnection()
                except Exception as e:
                    logger.warning("AirSim reconnect after nav: %s", e)
                    break

            # ── EMERGENCY abort: poll /status while navigating; if the
            # backend has flipped flightStatus to EMERGENCY (operator hit
            # the EMERGENCY button), kill the nav_worker subprocess and
            # invoke AirSim landAsync() directly. This guarantees the drone
            # stops obeying nav_worker velocity commands and descends now.
            if (is_navigating and nav_proc[0] is not None
                    and (now - last_emergency_check) >= EMERGENCY_CHECK_INTERVAL):
                last_emergency_check = now
                try:
                    _st = check_nav_status(bridge)
                except Exception:
                    _st = None
                if _st and str(_st.get("flightStatus", "")).upper() == "EMERGENCY":
                    logger.warning("EMERGENCY received mid-nav — killing nav_worker and landing")
                    emit_status("emergency", reason="operator abort")
                    try:
                        nav_proc[0].kill()
                    except Exception as e:
                        logger.warning("Failed to kill nav_worker: %s", e)
                    try:
                        client.landAsync().join()
                        logger.info("AirSim landAsync() completed")
                    except Exception as e:
                        logger.warning("landAsync failed: %s", e)
                    # Let the existing nav-complete branch reap nav_thread on next iteration.

            # ── Check for navigation commands ──
            if (now - last_nav_check >= NAV_CHECK_INTERVAL
                    and not is_navigating):
                last_nav_check = now
                nav_status = check_nav_status(bridge)
                if nav_status:
                    flight_status = nav_status.get("flightStatus", "")
                    is_nav_requested = nav_status.get("navigating", False) or nav_status.get("isNavigating", False)
                    goal_x = nav_status.get("goalNedX")
                    goal_y = nav_status.get("goalNedY")

                    if is_nav_requested and goal_x is not None and goal_y is not None:
                        logger.info(
                            "Navigation requested! Goal=[%.1f, %.1f] (flightStatus=%s)",
                            goal_x, goal_y, flight_status,
                        )
                        emit_status("navigating", goalX=goal_x, goalY=goal_y)
                        is_navigating = True
                        nav_result[0] = None

                        # Navigation runs in a subprocess (nav_worker.py) which has
                        # its own Python interpreter and tornado IOLoop.  No need to
                        # close the main AirSim client here.

                        nav_thread = threading.Thread(
                            target=_nav_thread_fn,
                            args=(bridge, goal_x, goal_y),
                            daemon=True,
                        )
                        nav_thread.start()

            # ── Active liveness probe: detect AirSim shutdown in <=5s ──
            # If the user closes AirSim while we're idle, msgpackrpc calls
            # may hang on a half-open socket. A direct TCP probe catches
            # this immediately and forces a reconnect cycle.
            if not is_navigating and (now - last_airsim_probe) >= AIRSIM_PROBE_INTERVAL:
                last_airsim_probe = now
                if not is_airsim_available(timeout=1.0):
                    logger.warning("AirSim TCP probe failed — port closed, reconnecting")
                    emit_status("reconnecting", reason="AirSim port closed")
                    try:
                        client = None
                    except Exception:
                        pass
                    break

            # ── Stream telemetry (continues during navigation too) ──
            # The planner runs in a SUBPROCESS (nav_worker.py) with its own
            # Python interpreter and tornado IOLoop, so the main bridge's
            # AirSim client is the only one in this process. AirSim's RPC
            # server handles concurrent client connections fine, so we keep
            # polling at TELEMETRY_INTERVAL even during navigation. This
            # guarantees the dashboard never goes OFFLINE mid-flight and
            # gives ms-precision motion monitoring (speed, altitude, NED).
            try:
                telemetry = build_telemetry(client, start_time)
                ok = bridge.send_telemetry(telemetry)
                if ok:
                    sent_count += 1
                    consecutive_fails = 0
                    # Log every ~10 seconds regardless of rate to avoid spam
                    # at 20 Hz (~200 packets/10s).
                    log_every = max(10, int(round(10.0 / max(TELEMETRY_INTERVAL, 0.001))))
                    if sent_count % log_every == 0:
                        emit_status("streaming", count=sent_count)
                        logger.info("Streamed %d telemetry packets", sent_count)
                else:
                    consecutive_fails += 1
                    logger.warning("Telemetry send failed (%d consecutive)",
                                   consecutive_fails)
            except Exception as e:
                consecutive_fails += 1
                if not is_navigating:
                    logger.warning("Telemetry error: %s (%d consecutive)",
                                   e, consecutive_fails)
                else:
                    # During navigation, AirSim client may be temporarily
                    # disrupted by planner reset — silently retry
                    logger.debug("Telemetry read error during nav (expected): %s", e)
                    try:
                        client = airsim.MultirotorClient(
                            ip=AIRSIM_HOST, port=AIRSIM_PORT, timeout_value=5
                        )
                        client.confirmConnection()
                        consecutive_fails = 0
                    except Exception:
                        pass

            # If too many consecutive failures (and NOT navigating), reconnect.
            # Lowered from 10 -> 3: with timeout_value=5, this fails fast.
            if consecutive_fails >= 3 and not is_navigating:
                logger.warning("Too many failures, reconnecting...")
                emit_status("reconnecting", reason="Too many telemetry failures")
                break

            time.sleep(TELEMETRY_INTERVAL)

        # ── Disconnected or failed — loop back to retry ──
        logger.info("Connection cycle ended, looping back...")

    # ── Clean shutdown ──
    emit_status("shutdown")
    logger.info("Auto-bridge shut down cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
