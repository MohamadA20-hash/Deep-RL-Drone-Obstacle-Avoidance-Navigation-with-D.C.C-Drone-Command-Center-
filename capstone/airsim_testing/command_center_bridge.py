"""
Command Center Bridge - Connects NavRL Planner to Drone Command Center
======================================================================
This module bridges the NavRL city planner with the Spring Boot backend,
enabling real-time telemetry reporting and remote command reception.

Data Flow:
    NavRL Planner ──► Bridge ──► REST API ──► Command Center Backend
                                                    │
    NavRL Planner ◄── Bridge ◄── WebSocket ◄────────┘
                                     ▲
                                     │ (fallback: HTTP polling at 2 Hz)

Features:
    - WebSocket listener for real-time command reception (raw WS, not STOMP)
    - HTTP polling fallback when WebSocket is unavailable
    - NED ↔ GPS coordinate conversion for frontend map display
    - Thread-safe command queue for planner integration
    - Background telemetry push thread

Usage:
    # Standalone test (no AirSim needed):
    python command_center_bridge.py --test

    # Integrated with NavRL planner:
    from command_center_bridge import CommandCenterBridge, BridgeConfig
    bridge = CommandCenterBridge(BridgeConfig(drone_id=1))
    bridge.connect()
    bridge.start_command_listener()
    bridge.send_telemetry(planner.get_telemetry_snapshot())
"""

import requests
import json
import time
import math
import os
import threading
import logging
import queue
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Tuple, List
from enum import Enum

logger = logging.getLogger(__name__)

# Optional: websocket-client for real-time command reception
try:
    import websocket as ws_client  # websocket-client package
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False
    logger.info("websocket-client not installed — using HTTP polling only. "
                 "Install with: pip install websocket-client")


# ── Remote Command Types ───────────────────────────────────────────────

class RemoteCommand(Enum):
    """Commands receivable from the command center."""
    STOP = "STOP_AUTONOMOUS_NAV"
    EMERGENCY_LAND = "EMERGENCY_STOP"
    PAUSE = "PAUSE_NAV"
    RESUME = "RESUME_NAV"
    REPLAN = "FORCE_REPLAN"
    SET_GOAL = "SET_GOAL"
    CONFIG_UPDATE = "SET_PLANNER_CONFIG"


@dataclass
class CommandMessage:
    """A parsed command from the command center."""
    command: RemoteCommand
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ── NED ↔ GPS Coordinate Conversion ───────────────────────────────────

@dataclass
class GeoReference:
    """
    Home GPS position used as the NED frame origin.
    
    AirSim uses NED coordinates relative to PlayerStart. This class stores
    the GPS coordinates of that origin so we can convert NED positions to
    lat/lon for the frontend map display.
    
    Default: AirSim Blocks environment PlayerStart (Redmond, WA).
    """
    home_lat: float = 47.641468     # degrees
    home_lon: float = -122.140165   # degrees
    home_alt_msl: float = 122.0     # meters above mean sea level

    # Earth radius approximations for local tangent plane
    METERS_PER_DEG_LAT: float = 111_111.0  # ~111 km per degree latitude

    def meters_per_deg_lon(self) -> float:
        """Longitude meters/degree varies with latitude."""
        return self.METERS_PER_DEG_LAT * math.cos(math.radians(self.home_lat))

    def ned_to_gps(self, ned_x: float, ned_y: float, ned_z: float = 0.0
                   ) -> Tuple[float, float, float]:
        """
        Convert NED (North-East-Down) meters to GPS (lat, lon, alt_msl).
        
        NED convention: X=North, Y=East, Z=Down (negative = above ground)
        
        Args:
            ned_x: Meters north of home
            ned_y: Meters east of home  
            ned_z: Meters down from home (negative = up)
        
        Returns:
            (latitude, longitude, altitude_msl)
        """
        lat = self.home_lat + (ned_x / self.METERS_PER_DEG_LAT)
        lon = self.home_lon + (ned_y / self.meters_per_deg_lon())
        alt = self.home_alt_msl - ned_z  # NED z is down; subtract to get MSL
        return (round(lat, 7), round(lon, 7), round(alt, 2))

    def gps_to_ned(self, lat: float, lon: float, alt_msl: float = None
                   ) -> Tuple[float, float, float]:
        """
        Convert GPS (lat, lon, alt_msl) to NED meters relative to home.
        
        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            alt_msl: Altitude above mean sea level (meters). If None, z=0.
        
        Returns:
            (ned_x, ned_y, ned_z)
        """
        ned_x = (lat - self.home_lat) * self.METERS_PER_DEG_LAT
        ned_y = (lon - self.home_lon) * self.meters_per_deg_lon()
        ned_z = -(alt_msl - self.home_alt_msl) if alt_msl is not None else 0.0
        return (round(ned_x, 3), round(ned_y, 3), round(ned_z, 3))


# ── Bridge Config ──────────────────────────────────────────────────────

@dataclass
class BridgeConfig:
    """Configuration for the command center connection."""
    base_url: str = "http://localhost:8080/api"
    ws_url: str = "ws://localhost:8080/ws/telemetry"  # Raw WebSocket endpoint
    drone_id: str = "1"                 # UUID or numeric ID from command center
    auth_token: Optional[str] = None
    auth_username: Optional[str] = None  # For auto-login
    auth_password: Optional[str] = None  # For auto-login
    telemetry_interval: float = 0.5      # seconds between telemetry pushes
    heartbeat_interval: float = 5.0      # seconds between heartbeat checks
    command_poll_interval: float = 0.5   # seconds between HTTP command polls
    retry_max: int = 3
    retry_delay: float = 2.0
    timeout: float = 5.0
    enable_websocket: bool = True        # Try WebSocket first, fallback to poll
    enable_gps: bool = True              # Include lat/lon in telemetry
    geo_ref: GeoReference = field(default_factory=GeoReference)

    # Debounce window (seconds) for non-safety commands (REPLAN / PAUSE /
    # RESUME / SET_GOAL / CONFIG_UPDATE). When an operator mashes the same
    # button or two operators issue overlapping commands, the WebSocket can
    # deliver many duplicates in a few hundred milliseconds. The planner
    # would then pop them mid-dodge and reset its A* state machine while
    # the reactive RL was mid-manoeuvre. Drop duplicate commands of the
    # same type that arrive within this window. STOP / EMERGENCY_LAND are
    # NEVER debounced (safety).
    command_debounce_window: float = 1.0

    def __post_init__(self):
        if bool(self.auth_username) != bool(self.auth_password):
            raise ValueError("Both auth_username and auth_password must be set, or neither")


class CommandCenterBridge:
    """
    Bridge between NavRL city planner and the drone command center backend.
    
    Responsibilities:
        1. Push telemetry data (NED position + GPS coords) to REST API
        2. Receive navigation commands via WebSocket (primary) or HTTP polling (fallback)
        3. Report navigation status changes (NAVIGATING, REPLANNING, etc.)
        4. Sync planner config updates from command center
        5. Thread-safe command queue for planner loop integration
    """

    def __init__(self, config: Optional[BridgeConfig] = None):
        self.config = config or BridgeConfig()
        self.geo = self.config.geo_ref
        self._session = requests.Session()
        self._session.timeout = self.config.timeout
        self._running = False
        self._telemetry_thread: Optional[threading.Thread] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._ws_app: Optional[Any] = None
        self._ws_connected = False
        self._command_queue: queue.Queue = queue.Queue()
        self._command_callback: Optional[Callable] = None
        # Per-command-type timestamp of the last enqueued message, used by
        # _enqueue_command() to debounce rapid duplicates from a flooded
        # operator UI. Safety commands bypass this map.
        self._last_enqueue_ts: Dict[RemoteCommand, float] = {}
        self._enqueue_lock = threading.Lock()
        self._last_telemetry: Optional[Dict] = None
        self._pending_telemetry: Optional[Dict] = None  # Thread-safe snapshot for background send
        self._telemetry_lock = threading.Lock()
        self._connected = False
        self._paused = False    # Set by PAUSE command, cleared by RESUME
        
        if self.config.auth_token:
            self._session.headers['Authorization'] = f'Bearer {self.config.auth_token}'
        self._session.headers['Content-Type'] = 'application/json'

    # ── Authentication ──────────────────────────────────────────────────

    def login(self, username: str = None, password: str = None) -> bool:
        """
        Authenticate with the command center and obtain a JWT token.
        
        Args:
            username: Override config username
            password: Override config password
        
        Returns:
            True if login succeeded and token was set.
        """
        user = username or self.config.auth_username
        passwd = password or self.config.auth_password
        if not user or not passwd:
            logger.warning("No credentials provided for login")
            return False
        
        # Auth endpoints are at /api/auth/login
        url = f"{self.config.base_url}/auth/login"
        payload = {"username": user, "password": passwd}
        try:
            resp = self._session.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                # Handle wrapped response: {"data": {"token": "..."}}
                token_data = data.get("data", data)
                token = token_data.get("token")
                if token:
                    self.config.auth_token = token
                    self._session.headers['Authorization'] = f'Bearer {token}'
                    logger.info(f"Authenticated as {user}")
                    return True
                else:
                    logger.error("Login response missing token")
                    return False
            else:
                logger.error(f"Login failed: HTTP {resp.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Login request failed: {e}")
            return False

    # ── Connection Management ──────────────────────────────────────────

    def connect(self) -> bool:
        """
        Connect to the command center.
        
        If auth credentials are configured but no token exists, auto-login first.
        Then verify the drone exists.
        """
        # Auto-login if credentials provided but no token yet
        if not self.config.auth_token and self.config.auth_username:
            if not self.login():
                logger.error("Auto-login failed")
                return False
        
        # Auto-discover drone ID if set to 'auto'
        if self.config.drone_id == 'auto':
            if not self._discover_drone_id():
                return False
        
        url = f"{self.config.base_url}/drones/{self.config.drone_id}"
        for attempt in range(self.config.retry_max):
            try:
                resp = self._session.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    drone = data.get('data', data)
                    logger.info(f"Connected to command center. Drone: {drone.get('name', 'Unknown')}")
                    self._connected = True
                    return True
                elif resp.status_code == 401:
                    logger.error("Authentication failed. Check auth token.")
                    return False
                else:
                    logger.warning(f"Drone {self.config.drone_id} not found (HTTP {resp.status_code})")
            except requests.ConnectionError:
                logger.warning(f"Connection attempt {attempt+1}/{self.config.retry_max} failed")
                if attempt < self.config.retry_max - 1:
                    time.sleep(self.config.retry_delay)
        
        logger.error(f"Could not connect to command center at {self.config.base_url}")
        return False

    def _discover_drone_id(self) -> bool:
        """Auto-discover drone ID by fetching the first drone from /api/drones."""
        try:
            resp = self._session.get(f"{self.config.base_url}/drones")
            if resp.status_code == 200:
                data = resp.json()
                content = data.get('data', data)
                # Handle paginated response: {data: {content: [...]}}
                drones = content.get('content', content) if isinstance(content, dict) else content
                if drones and len(drones) > 0:
                    self.config.drone_id = str(drones[0].get('id'))
                    logger.info(f"Auto-discovered drone ID: {self.config.drone_id}")
                    return True
                else:
                    logger.error("No drones found in command center")
                    return False
            else:
                logger.error(f"Cannot list drones: HTTP {resp.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Drone discovery failed: {e}")
            return False

    def disconnect(self):
        """Stop all threads and clean up."""
        self._running = False
        # Stop WebSocket
        if self._ws_app:
            try:
                self._ws_app.close()
            except Exception:
                pass
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3)
        # Stop polling thread
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=3)
        # Stop telemetry thread
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=3)
        self._ws_connected = False
        self._connected = False
        logger.info("Disconnected from command center")

    # ── WebSocket Command Listener ─────────────────────────────────────

    def start_command_listener(self):
        """
        Start listening for remote commands.
        
        Tries WebSocket first (real-time). If websocket-client is not
        installed or the connection fails, falls back to HTTP polling.
        Commands are placed in a thread-safe queue that the planner
        loop can drain with pop_command().
        """
        if self._running:
            logger.warning("Command listener already running")
            return

        self._running = True

        if self.config.enable_websocket and HAS_WEBSOCKET:
            self._start_websocket_listener()
        else:
            reason = "disabled" if not self.config.enable_websocket else "websocket-client not installed"
            logger.info(f"WebSocket {reason} — using HTTP polling")
            self._start_poll_listener()

    def _start_websocket_listener(self):
        """Connect to the raw WebSocket at /ws/telemetry and listen for commands."""
        
        def on_open(ws):
            self._ws_connected = True
            logger.info(f"WebSocket connected to {self.config.ws_url}")
            # Subscribe to our drone's updates
            subscribe_msg = json.dumps({
                "action": "subscribe",
                "droneId": str(self.config.drone_id)
            })
            ws.send(subscribe_msg)
            logger.info(f"Subscribed to drone {self.config.drone_id}")

        def on_message(ws, message):
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")
                
                if msg_type == "command":
                    # Command message from backend
                    self._handle_ws_command(data)
                elif msg_type == "droneStatus":
                    # Status update — extract inner data object
                    inner = data.get("data", data)
                    status = ""
                    if isinstance(inner, dict):
                        status = inner.get("flightStatus", inner.get("status", ""))
                    else:
                        status = data.get("status", "")
                    self._check_status_for_commands(status, data)
                elif msg_type == "pong":
                    pass  # Heartbeat response
                elif msg_type == "subscribed":
                    logger.info(f"Subscription confirmed: {data.get('droneId')}")
                elif msg_type == "error":
                    logger.warning(f"WebSocket error from server: {data.get('message')}")
                else:
                    logger.debug(f"WS message type={msg_type}: {str(data)[:200]}")
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON WebSocket message: {message[:200]}")

        def on_error(ws, error):
            logger.warning(f"WebSocket error: {error}")
            self._ws_connected = False

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed (code={close_status_code})")
            self._ws_connected = False
            # Auto-fallback to polling if still running
            if self._running:
                logger.info("Falling back to HTTP command polling")
                self._start_poll_listener()

        def _ws_thread_func():
            backoff = 3
            while self._running:
                try:
                    self._ws_app = ws_client.WebSocketApp(
                        self.config.ws_url,
                        on_open=on_open,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close,
                    )
                    # run_forever blocks until the connection drops
                    self._ws_app.run_forever(
                        ping_interval=self.config.heartbeat_interval,
                        ping_timeout=max(self.config.heartbeat_interval - 2, 2)
                    )
                    backoff = 3  # Reset on clean disconnect
                except Exception as e:
                    logger.error(f"WebSocket thread error: {e}")
                
                if self._running:
                    logger.info("WebSocket reconnecting in %ds...", backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)  # Exponential backoff, cap at 60s

        self._ws_thread = threading.Thread(target=_ws_thread_func, daemon=True, 
                                            name="ws-command-listener")
        self._ws_thread.start()
        logger.info("WebSocket command listener started")

    def _handle_ws_command(self, data: Dict):
        """Parse a command message from WebSocket and enqueue it."""
        # The backend sends: {"type":"command","message":null,"data":{...}}
        inner = data.get("data", data)
        if isinstance(inner, dict):
            cmd_type = inner.get("commandType", inner.get("command", ""))
        else:
            cmd_type = data.get("commandType", data.get("command", ""))
        try:
            cmd = RemoteCommand(cmd_type)
        except ValueError:
            logger.warning(f"Unknown command type via WS: {cmd_type}")
            return

        msg = CommandMessage(
            command=cmd,
            payload=inner.get("payload", inner) if isinstance(inner, dict) else data,
        )
        if self._enqueue_command(msg):
            logger.info(f"Enqueued WS command: {cmd.name}")

    def _check_status_for_commands(self, status: str, data: Dict):
        """
        Infer commands from drone status transitions.
        For example, if the backend changes status to IDLE while we're
        navigating, treat it as a STOP command.
        """
        # This is intentionally conservative — only STOP is inferred
        if status in ("IDLE", "LANDED") and self._connected:
            msg = CommandMessage(
                command=RemoteCommand.STOP,
                payload={"source": "status_transition", "new_status": status},
            )
            # STOP is a safety command and bypasses the debounce window.
            self._enqueue_command(msg)
            logger.info(f"Inferred STOP from status change to {status}")

    # ── HTTP Command Polling (Fallback) ────────────────────────────────

    def _start_poll_listener(self):
        """Poll the NavRL status endpoint for pending commands."""
        if self._poll_thread and self._poll_thread.is_alive():
            return  # Already polling

        def _poll_loop():
            logger.info(f"HTTP command polling started (interval={self.config.command_poll_interval}s)")
            last_status = None
            while self._running and not self._ws_connected:
                try:
                    status = self.get_navrl_status()
                    if status:
                        current = status.get("navigationStatus", status.get("flightStatus", ""))
                        # Detect status transitions that imply commands
                        if last_status and current != last_status:
                            if current in ("IDLE", "LANDED"):
                                self._enqueue_command(CommandMessage(
                                    command=RemoteCommand.STOP,
                                    payload={"source": "poll", "new_status": current}
                                ))
                        last_status = current
                        
                        # Check for pending config update flag
                        if status.get("configUpdatePending"):
                            self._enqueue_command(CommandMessage(
                                command=RemoteCommand.CONFIG_UPDATE,
                                payload=status.get("pendingConfig", {})
                            ))
                except Exception as e:
                    logger.debug(f"Poll error: {e}")
                
                time.sleep(self.config.command_poll_interval)
            
            logger.info("HTTP command polling stopped")

        self._poll_thread = threading.Thread(target=_poll_loop, daemon=True,
                                              name="http-command-poll")
        self._poll_thread.start()

    # ── Command Queue (Thread-Safe, Planner Integration) ───────────────

    # Commands that must NEVER be debounced — losing one of these because
    # the operator clicked twice could put the drone into a wall.
    _SAFETY_COMMANDS = frozenset({
        RemoteCommand.STOP,
        RemoteCommand.EMERGENCY_LAND,
    })

    def _enqueue_command(self, msg: CommandMessage) -> bool:
        """
        Push a command onto the queue, debouncing rapid duplicates of the
        same non-safety command type within `command_debounce_window`
        seconds.

        This is the single entry point for ALL command sources (WebSocket,
        HTTP poll, status-transition inference, test helpers). Routing
        every put through here guarantees that an operator mashing
        "FORCE_REPLAN" 10 times in 200 ms is collapsed into a single
        replan, instead of resetting the planner's A* state machine 10
        times while the reactive RL is mid-dodge.

        Returns:
            True  — message was enqueued.
            False — message was dropped as a duplicate within the debounce
                    window (caller may want to skip its log line).
        """
        cmd = msg.command
        if cmd in self._SAFETY_COMMANDS:
            self._command_queue.put(msg)
            return True

        window = max(0.0, float(self.config.command_debounce_window))
        if window <= 0.0:
            self._command_queue.put(msg)
            return True

        now = time.time()
        with self._enqueue_lock:
            last = self._last_enqueue_ts.get(cmd, 0.0)
            if now - last < window:
                logger.debug(
                    "Debounced duplicate %s (%.2fs since last)",
                    cmd.name, now - last,
                )
                return False
            self._last_enqueue_ts[cmd] = now
        self._command_queue.put(msg)
        return True

    def pop_command(self) -> Optional[CommandMessage]:
        """
        Non-blocking pop from the command queue.
        
        Call this inside the planner's navigation loop to check
        for remote commands each iteration.
        
        Returns:
            CommandMessage if available, None otherwise.
        """
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None

    def drain_commands(self) -> List[CommandMessage]:
        """Pop all pending commands (useful for batch processing)."""
        cmds = []
        while True:
            cmd = self.pop_command()
            if cmd is None:
                break
            cmds.append(cmd)
        return cmds

    @property
    def is_paused(self) -> bool:
        """Whether navigation is currently paused by remote command."""
        return self._paused

    def set_paused(self, paused: bool):
        """Set pause state (called by planner when handling PAUSE/RESUME)."""
        self._paused = paused

    # ── Telemetry Reporting ────────────────────────────────────────────

    def send_telemetry(self, telemetry_data: Dict[str, Any]) -> bool:
        """
        Push a single telemetry snapshot to the command center.
        
        Automatically appends GPS coordinates (latitude, longitude) if
        NED position fields are present and GPS conversion is enabled.
        
        Args:
            telemetry_data: Dict matching TelemetryCreateRequest fields.
        
        Returns:
            True if telemetry was accepted by the server.
        """
        telemetry_data['droneId'] = self.config.drone_id
        
        # Auto-convert NED → GPS for frontend map display
        if self.config.enable_gps:
            ned_x = telemetry_data.get('positionNedX')
            ned_y = telemetry_data.get('positionNedY')
            ned_z = telemetry_data.get('positionNedZ', 0.0)
            if ned_x is not None and ned_y is not None:
                lat, lon, alt_msl = self.geo.ned_to_gps(ned_x, ned_y, ned_z)
                telemetry_data.setdefault('latitude', lat)
                telemetry_data.setdefault('longitude', lon)
        
        url = f"{self.config.base_url}/telemetry"
        
        try:
            resp = self._session.post(url, json=telemetry_data)
            if resp.status_code in (200, 201):
                self._last_telemetry = telemetry_data
                return True
            else:
                logger.warning(f"Telemetry rejected: HTTP {resp.status_code}")
                return False
        except requests.RequestException as e:
            logger.error(f"Telemetry send failed: {e}")
            return False

    def ned_to_gps(self, ned_x: float, ned_y: float, ned_z: float = 0.0
                   ) -> Tuple[float, float, float]:
        """Convenience: convert NED position to GPS (lat, lon, alt_msl)."""
        return self.geo.ned_to_gps(ned_x, ned_y, ned_z)

    def gps_to_ned(self, lat: float, lon: float, alt_msl: float = None
                   ) -> Tuple[float, float, float]:
        """Convenience: convert GPS to NED position."""
        return self.geo.gps_to_ned(lat, lon, alt_msl)

    def build_telemetry_from_planner(self, planner) -> Dict[str, Any]:
        """
        Extract telemetry data from a NavRLCityPlanner instance.
        
        Args:
            planner: NavRLCityPlanner instance with active navigation state
        
        Returns:
            Dict ready to pass to send_telemetry()
        """
        # Get AirSim state
        state = planner.bridge.client.getMultirotorState()
        pos = state.kinematics_estimated.position
        vel = state.kinematics_estimated.linear_velocity
        orientation = state.kinematics_estimated.orientation
        
        # Convert quaternion to euler (degrees)
        import math
        q = orientation
        # Yaw
        siny_cosp = 2.0 * (q.w_val * q.z_val + q.x_val * q.y_val)
        cosy_cosp = 1.0 - 2.0 * (q.y_val * q.y_val + q.z_val * q.z_val)
        yaw_deg = math.degrees(math.atan2(siny_cosp, cosy_cosp))
        # Pitch
        sinp = 2.0 * (q.w_val * q.y_val - q.z_val * q.x_val)
        sinp = max(-1.0, min(1.0, sinp))
        pitch_deg = math.degrees(math.asin(sinp))
        # Roll
        sinr_cosp = 2.0 * (q.w_val * q.x_val + q.y_val * q.z_val)
        cosr_cosp = 1.0 - 2.0 * (q.x_val * q.x_val + q.y_val * q.y_val)
        roll_deg = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
        
        # Battery (simulated — AirSim doesn't model battery)
        battery = max(0.0, 100.0 - (time.time() - getattr(planner, '_start_time', time.time())) / 36.0)
        
        # Navigation metrics
        total_stuck = getattr(planner, 'stuck_replan_count', 0)
        total_proactive = getattr(planner, 'proactive_replan_count', 0)
        
        # Distance metrics
        goal = getattr(planner, 'final_goal', None)
        dist_to_goal = 0.0
        optimal_dist = 0.0
        if goal is not None:
            dx = goal[0] - pos.x_val
            dy = goal[1] - pos.y_val
            dist_to_goal = (dx*dx + dy*dy) ** 0.5
            optimal_dist = getattr(planner, 'initial_goal_distance', dist_to_goal)
        
        path_length = getattr(planner, 'total_distance_traveled', 0.0)
        efficiency = (optimal_dist / path_length * 100.0) if path_length > 0 else 0.0
        
        # Obstacle info
        grid = getattr(planner, 'occupancy_grid', None)
        mapped_cells = int(grid.grid.sum()) if grid is not None else 0
        
        closest_obs = getattr(planner, '_closest_obstacle_distance', 4.0)
        speed = (vel.x_val**2 + vel.y_val**2) ** 0.5

        # LiDAR radar scan — bin raw AirSim point cloud into 36 sectors
        import numpy as np
        LIDAR_MAX = 4.0
        LIDAR_SECTORS = 36
        LIDAR_DEG = 360.0 / LIDAR_SECTORS
        radar_sectors = [LIDAR_MAX] * LIDAR_SECTORS
        try:
            lidar_data = planner.bridge.client.getLidarData('LidarSensor1', 'Drone1')
            if len(lidar_data.point_cloud) >= 3:
                pts = np.array(lidar_data.point_cloud).reshape(-1, 3)
                dists = np.sqrt(np.sum(pts ** 2, axis=1))
                valid_mask = dists > 0.15
                if np.any(valid_mask):
                    vx_pts = pts[valid_mask, 0]
                    vy_pts = pts[valid_mask, 1]
                    vd = dists[valid_mask]
                    angles_deg = (np.degrees(np.arctan2(vy_pts, vx_pts)) + 360) % 360
                    bins = np.clip((angles_deg / LIDAR_DEG).astype(int), 0, LIDAR_SECTORS - 1)
                    for bi, di in zip(bins, vd):
                        if di < radar_sectors[bi]:
                            radar_sectors[bi] = float(di)
        except Exception:
            pass
        
        # Altitude mode
        alt_ctrl = getattr(planner, 'altitude_controller', None)
        alt_mode = "CRUISE"
        if alt_ctrl is not None:
            mode = getattr(alt_ctrl, 'mode', None)
            if mode is not None:
                alt_mode = mode.name if hasattr(mode, 'name') else str(mode)
        
        # Best effort
        best_effort = getattr(planner, 'best_effort_active', False)
        
        # Collision count
        collision_count = getattr(planner, 'collision_count', 0)
        
        # Current path
        waypoints = getattr(planner, 'current_plan', [])
        wp_count = len(waypoints) if waypoints else 0

        return {
            'droneId': self.config.drone_id,
            'velocityX': round(vel.x_val, 4),
            'velocityY': round(vel.y_val, 4),
            'velocityZ': round(vel.z_val, 4),
            'yaw': round(yaw_deg, 2),
            'pitch': round(pitch_deg, 2),
            'roll': round(roll_deg, 2),
            'batteryLevel': round(battery, 1),
            'altitude': round(-pos.z_val, 2),  # NED z is negative = above ground
            'obstacleDistance': round(closest_obs, 2),
            'positionNedX': round(pos.x_val, 3),
            'positionNedY': round(pos.y_val, 3),
            'positionNedZ': round(pos.z_val, 3),
            'altitudeMode': alt_mode,
            'stuckReplanCount': total_stuck,
            'proactiveReplanCount': total_proactive,
            'navigationEfficiency': round(efficiency, 1),
            'pathLength': round(path_length, 2),
            'optimalDistance': round(optimal_dist, 2),
            'distanceToGoal': round(dist_to_goal, 2),
            'mappedObstacleCells': mapped_cells,
            'closestObstacleDistance': round(closest_obs, 2),
            'bestEffortActive': best_effort,
            'collisionCount': collision_count,
            'currentPathWaypointCount': wp_count,
            'navrlSpeed': round(speed, 3),
            'lidarScan': json.dumps([round(d, 2) for d in radar_sectors]),
        }

    # ── Navigation Commands ────────────────────────────────────────────

    def set_goal(self, goal_x: float, goal_y: float, 
                 base_altitude: Optional[float] = None) -> bool:
        """Send a navigation goal to the command center."""
        url = f"{self.config.base_url}/navrl/drones/{self.config.drone_id}/goal"
        payload = {'goalX': goal_x, 'goalY': goal_y}
        if base_altitude is not None:
            payload['baseAltitude'] = base_altitude
        try:
            resp = self._session.post(url, json=payload)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Set goal failed: {e}")
            return False

    def start_navigation(self, goal_x: Optional[float] = None,
                         goal_y: Optional[float] = None) -> bool:
        """Start autonomous navigation."""
        url = f"{self.config.base_url}/navrl/drones/{self.config.drone_id}/start"
        payload = {}
        if goal_x is not None and goal_y is not None:
            payload = {'goalX': goal_x, 'goalY': goal_y}
        try:
            resp = self._session.post(url, json=payload)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Start navigation failed: {e}")
            return False

    def stop_navigation(self) -> bool:
        """Stop autonomous navigation."""
        url = f"{self.config.base_url}/navrl/drones/{self.config.drone_id}/stop"
        try:
            resp = self._session.post(url)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Stop navigation failed: {e}")
            return False

    def get_navrl_status(self) -> Optional[Dict]:
        """Get current NavRL navigation status from the command center."""
        url = f"{self.config.base_url}/navrl/drones/{self.config.drone_id}/status"
        try:
            resp = self._session.get(url)
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def get_default_config(self) -> Optional[Dict]:
        """Fetch default planner config from the command center."""
        url = f"{self.config.base_url}/navrl/config/defaults"
        try:
            resp = self._session.get(url)
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            return None

    def update_planner_config(self, config_overrides: Dict) -> bool:
        """Push planner config updates to the command center."""
        url = f"{self.config.base_url}/navrl/drones/{self.config.drone_id}/config"
        try:
            resp = self._session.put(url, json=config_overrides)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Config update failed: {e}")
            return False

    # ── Mission Management ─────────────────────────────────────────────

    def get_missions(self, status: str = None) -> Optional[List[Dict]]:
        """Fetch missions from the command center, optionally filtered by status."""
        url = f"{self.config.base_url}/missions"
        if status:
            url = f"{url}/status/{status}"
        try:
            resp = self._session.get(url)
            if resp.status_code == 200:
                data = resp.json()
                payload = data.get('data', data)
                # Handle paginated response
                if isinstance(payload, dict) and 'content' in payload:
                    return payload['content']
                return payload if isinstance(payload, list) else [payload]
            return None
        except requests.RequestException as e:
            logger.error(f"Fetch missions failed: {e}")
            return None

    def get_mission(self, mission_id: str) -> Optional[Dict]:
        """Fetch a single mission with its waypoints."""
        url = f"{self.config.base_url}/missions/{mission_id}"
        try:
            resp = self._session.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('data', data)
            return None
        except requests.RequestException as e:
            logger.error(f"Fetch mission {mission_id} failed: {e}")
            return None

    def get_drone_missions(self, status: str = None) -> Optional[List[Dict]]:
        """Fetch missions assigned to this drone."""
        url = f"{self.config.base_url}/missions/drone/{self.config.drone_id}"
        try:
            resp = self._session.get(url)
            if resp.status_code == 200:
                data = resp.json()
                payload = data.get('data', data)
                missions = payload.get('content', payload) if isinstance(payload, dict) else payload
                if status and isinstance(missions, list):
                    missions = [m for m in missions if m.get('status') == status]
                return missions
            return None
        except requests.RequestException as e:
            logger.error(f"Fetch drone missions failed: {e}")
            return None

    def update_mission_status(self, mission_id: str, action: str) -> bool:
        """
        Update mission status via backend API.
        
        Args:
            mission_id: Mission UUID
            action: One of 'start', 'pause', 'resume', 'complete', 'abort'
        """
        url = f"{self.config.base_url}/missions/{mission_id}/{action}"
        try:
            params = {}
            if action == 'complete':
                params = {'success': 'true'}
            resp = self._session.patch(url, params=params)
            if resp.status_code == 200:
                logger.info(f"Mission {mission_id} → {action}")
                return True
            logger.warning(f"Mission {action} failed: HTTP {resp.status_code}")
            return False
        except requests.RequestException as e:
            logger.error(f"Mission status update failed: {e}")
            return False

    def extract_waypoints_ned(self, mission: Dict) -> List[Tuple[float, float]]:
        """
        Extract NED (x, y) waypoints from a mission.
        
        If waypoints have nedX/nedY, use those directly.
        Otherwise convert from lat/lon using geo reference.
        
        Returns:
            List of (ned_x, ned_y) tuples in order.
        """
        waypoints = mission.get('waypoints', [])
        if not waypoints:
            # Fall back to mission-level goal
            gx = mission.get('goalNedX')
            gy = mission.get('goalNedY')
            if gx is not None and gy is not None:
                return [(gx, gy)]
            return []
        
        # Sort by sequence order
        waypoints = sorted(waypoints, key=lambda w: w.get('sequenceOrder', 0))
        
        ned_points = []
        for wp in waypoints:
            nx = wp.get('nedX')
            ny = wp.get('nedY')
            if nx is not None and ny is not None:
                ned_points.append((nx, ny))
            else:
                # Convert GPS to NED
                lat = wp.get('latitude', 0)
                lon = wp.get('longitude', 0)
                alt = wp.get('altitude')
                ned_x, ned_y, _ = self.geo.gps_to_ned(lat, lon, alt)
                ned_points.append((ned_x, ned_y))
        
        return ned_points

    def execute_mission(self, planner, mission_id: str = None,
                        min_altitude: float = None,
                        timeout_per_wp: float = 120.0,
                        return_to_base: bool = True) -> Optional[Dict]:
        """
        Fetch and execute a mission from the command center.
        
        Fetches the mission's waypoints, navigates to each using the
        NavRL planner, and reports progress back to the backend.
        
        Args:
            planner: NavRLCityPlanner instance
            mission_id: Specific mission UUID. If None, picks the first
                        CREATED/PLANNED mission assigned to this drone.
            min_altitude: Override mission altitude (meters, positive)
            timeout_per_wp: Max seconds per waypoint
            return_to_base: Whether to return home after all waypoints
        
        Returns:
            Mission results dict, or None if no mission found.
        """
        import numpy as np
        
        # Find mission
        if mission_id:
            mission = self.get_mission(mission_id)
        else:
            missions = self.get_drone_missions()
            if not missions:
                logger.warning("No missions found for this drone")
                return None
            # Pick first actionable mission
            mission = None
            for m in missions:
                if m.get('status') in ('CREATED', 'PLANNED'):
                    mission = m
                    break
            if not mission:
                logger.warning("No CREATED/PLANNED missions found")
                return None
        
        if not mission:
            logger.error(f"Mission {mission_id} not found")
            return None
        
        mid = mission['id']
        mname = mission.get('name', 'Unnamed')
        logger.info(f"Executing mission: {mname} ({mid})")
        
        # Extract waypoints
        ned_waypoints = self.extract_waypoints_ned(mission)
        if not ned_waypoints:
            logger.error("Mission has no navigable waypoints")
            return None
        
        # Get altitude from mission or default
        base_alt = min_altitude or mission.get('baseAltitude') or 10.0
        
        # Start mission on backend
        self.update_mission_status(mid, 'start')
        
        # Execute with planner
        wp_arrays = [np.array(wp) for wp in ned_waypoints]
        logger.info(f"Mission has {len(wp_arrays)} waypoints, base altitude={base_alt}m")
        
        try:
            result = planner.run_city_mission(
                waypoints=wp_arrays,
                return_to_base=return_to_base,
                min_altitude=base_alt,
                timeout_per_wp=timeout_per_wp,
            )
            
            # Report completion
            if result.get('mission_success'):
                self.update_mission_status(mid, 'complete')
            else:
                self.update_mission_status(mid, 'abort')
            
            logger.info(f"Mission {mname}: {'SUCCESS' if result.get('mission_success') else 'FAILED'}")
            return result
            
        except Exception as e:
            logger.error(f"Mission execution error: {e}")
            self.update_mission_status(mid, 'abort')
            return {'mission_success': False, 'error': str(e)}

    # ── Background Telemetry Thread ────────────────────────────────────

    def update_telemetry_snapshot(self, planner):
        """
        Build and cache telemetry data from the planner.
        
        MUST be called from the main thread (same thread as AirSim client)
        to avoid tornado IOLoop threading conflicts.
        """
        try:
            snapshot = self.build_telemetry_from_planner(planner)
            with self._telemetry_lock:
                self._pending_telemetry = snapshot
        except Exception as e:
            logger.debug(f"Snapshot build error: {e}")

    def start_telemetry_loop(self, planner, interval: Optional[float] = None):
        """
        Start a background thread that continuously pushes telemetry.
        
        The background thread only reads and sends cached snapshots.
        The main navigation loop must call update_telemetry_snapshot()
        to refresh the data (avoids AirSim threading issues).
        
        Args:
            planner: NavRLCityPlanner instance (used for initial snapshot only)
            interval: Override telemetry push interval (seconds)
        """
        if self._running:
            logger.warning("Telemetry loop already running")
            return

        self._running = True
        push_interval = interval or self.config.telemetry_interval

        def _loop():
            while self._running:
                try:
                    with self._telemetry_lock:
                        snapshot = self._pending_telemetry
                    if snapshot is not None:
                        self.send_telemetry(dict(snapshot))  # Send a copy
                    else:
                        logger.debug("No telemetry snapshot available yet")
                except Exception as e:
                    logger.error(f"Telemetry send error: {e}")
                time.sleep(push_interval)

        self._telemetry_thread = threading.Thread(target=_loop, daemon=True)
        self._telemetry_thread.start()
        logger.info(f"Telemetry loop started (interval={push_interval}s)")

    def stop_telemetry_loop(self):
        """Stop the background telemetry thread."""
        self._running = False
        if self._telemetry_thread:
            self._telemetry_thread.join(timeout=3)
            self._telemetry_thread = None
        logger.info("Telemetry loop stopped")

    # ── Utility ────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    def __repr__(self):
        status = "connected" if self._connected else "disconnected"
        return f"CommandCenterBridge(drone={self.config.drone_id}, {status})"


# ── Standalone Test ────────────────────────────────────────────────────

def _run_self_test():
    """Test the bridge without AirSim — verifies API connectivity + new features."""
    print("=" * 60)
    print("Command Center Bridge - Self Test")
    print("=" * 60)
    
    config = BridgeConfig(
        base_url="http://localhost:8080/api",
        drone_id="auto",
        auth_username="navrl_bridge",
        auth_password=os.environ.get("BRIDGE_AUTH_PASS", ""),
    )
    bridge = CommandCenterBridge(config)
    
    # Test 1: NED ↔ GPS conversion
    print("\n[1] Testing NED ↔ GPS conversion...")
    ned_pos = (100.0, -50.0, -15.0)  # 100m north, 50m west, 15m up
    lat, lon, alt = bridge.ned_to_gps(*ned_pos)
    print(f"    NED ({ned_pos[0]}, {ned_pos[1]}, {ned_pos[2]}) → GPS ({lat}, {lon}, {alt}m MSL)")
    ned_back = bridge.gps_to_ned(lat, lon, alt)
    print(f"    GPS → NED ({ned_back[0]}, {ned_back[1]}, {ned_back[2]})")
    err = max(abs(ned_pos[i] - ned_back[i]) for i in range(3))
    print(f"    Round-trip error: {err:.4f}m → {'✓ PASS' if err < 0.01 else '✗ FAIL'}")

    # Test 2: Connection
    print("\n[2] Testing HTTP connection...")
    if bridge.connect():
        print("    ✓ Connected to command center")
    else:
        print("    ✗ Could not connect (is the backend running?)")
        print("    Start it with: cd drone-command-center && ./mvnw spring-boot:run")
        return
    
    # Test 3: Send telemetry (with auto GPS)
    print("\n[3] Sending test telemetry (with NED→GPS auto-conversion)...")
    test_telemetry = {
        'droneId': 1,
        'velocityX': 1.2, 'velocityY': 0.5, 'velocityZ': -0.1,
        'yaw': 45.0, 'pitch': 2.0, 'roll': 0.5,
        'batteryLevel': 85.0, 'altitude': 12.0, 'obstacleDistance': 3.5,
        'positionNedX': 25.5, 'positionNedY': -10.3, 'positionNedZ': -12.0,
        'altitudeMode': 'CRUISE',
        'stuckReplanCount': 0, 'proactiveReplanCount': 1,
        'navigationEfficiency': 72.5,
        'pathLength': 45.2, 'optimalDistance': 32.8, 'distanceToGoal': 18.3,
        'mappedObstacleCells': 142, 'closestObstacleDistance': 3.5,
        'bestEffortActive': False, 'collisionCount': 0,
        'currentPathWaypointCount': 5, 'navrlSpeed': 1.3,
    }
    if bridge.send_telemetry(test_telemetry):
        lat = test_telemetry.get('latitude', 'N/A')
        lon = test_telemetry.get('longitude', 'N/A')
        print(f"    ✓ Telemetry accepted (auto GPS: {lat}, {lon})")
    else:
        print("    ✗ Telemetry rejected")
    
    # Test 4: Get default config
    print("\n[4] Fetching default planner config...")
    defaults = bridge.get_default_config()
    if defaults:
        print(f"    ✓ Got {len(defaults)} config parameters")
        for k, v in list(defaults.items())[:5]:
            print(f"      {k}: {v}")
        if len(defaults) > 5:
            print(f"      ... and {len(defaults) - 5} more")
    else:
        print("    ✗ Could not fetch config")
    
    # Test 5: Get NavRL status
    print("\n[5] Getting NavRL status...")
    status = bridge.get_navrl_status()
    if status:
        print(f"    ✓ Status: {json.dumps(status, indent=6)[:200]}")
    else:
        print("    ✗ Could not get status")
    
    # Test 6: Set goal
    print("\n[6] Setting navigation goal (50, 25)...")
    if bridge.set_goal(50.0, 25.0):
        print("    ✓ Goal accepted")
    else:
        print("    ✗ Goal rejected (drone may need to be airborne)")
    
    # Test 7: Command queue
    print("\n[7] Testing command queue...")
    bridge._command_queue.put(CommandMessage(command=RemoteCommand.PAUSE))
    bridge._command_queue.put(CommandMessage(command=RemoteCommand.RESUME))
    cmds = bridge.drain_commands()
    print(f"    ✓ Enqueued 2 → drained {len(cmds)}: {[c.command.name for c in cmds]}")
    
    # Test 8: WebSocket availability
    print(f"\n[8] WebSocket client available: {'✓ YES' if HAS_WEBSOCKET else '✗ NO (install websocket-client)'}")
    if HAS_WEBSOCKET:
        print("    Starting WebSocket listener (3s test)...")
        bridge.start_command_listener()
        time.sleep(3)
        ws_status = "connected" if bridge._ws_connected else "not connected (server may not be broadcasting)"
        print(f"    WebSocket: {ws_status}")
    
    bridge.disconnect()
    print("\n" + "=" * 60)
    print("Self test complete")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    import argparse
    parser = argparse.ArgumentParser(description="Command Center Bridge")
    parser.add_argument('--test', action='store_true', help='Run self-test')
    parser.add_argument('--url', default='http://localhost:8080/api', help='Backend URL')
    parser.add_argument('--drone-id', type=int, default=1, help='Drone ID')
    args = parser.parse_args()
    
    if args.test:
        _run_self_test()
    else:
        print("Use --test to run self-test, or import CommandCenterBridge in your code")
