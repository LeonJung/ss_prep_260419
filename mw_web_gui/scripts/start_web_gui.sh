#!/usr/bin/env bash
# Start the mw web GUI stack + cloudflared quick-tunnel and print the
# public URL at the end.
#
# Prereqs:
#   - colcon build done (so hfsm_executor, foxglove_bridge reachable)
#   - `source install/setup.bash` before running
#   - node + npm installed
#   - cloudflared installed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PKG_DIR/frontend"
# When invoked from install/ tree, prefer the source frontend if available.
if [[ ! -d "$FRONTEND_DIR" && -d "$MW_WS/src/mw_web_gui/frontend" ]]; then
  FRONTEND_DIR="$MW_WS/src/mw_web_gui/frontend"
fi
if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "[start_web_gui] frontend dir not found, set MW_WS to workspace root" >&2
  exit 1
fi

VITE_PORT="${VITE_PORT:-5173}"
DISPATCH_PORT="${DISPATCH_PORT:-5174}"
FG_PORT="${FG_PORT:-8765}"
RMW="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export RMW_IMPLEMENTATION="$RMW"
# Pick launch profile via env. Default = emulator-based Web GUI.
# Use LAUNCH=navigate to bring up the real TB3 Gazebo simulation with
# our task_manager + foxglove_bridge.
LAUNCH_PROFILE="${LAUNCH:-web_gui}"
case "$LAUNCH_PROFILE" in
  web_gui|emulator)  LAUNCH_FILE="web_gui.launch.py" ;;
  navigate|tb3)      LAUNCH_FILE="navigate_web_gui.launch.py"
                     export TURTLEBOT3_MODEL="${TURTLEBOT3_MODEL:-waffle}"
                     ;;
  *)
    if [[ "$LAUNCH_PROFILE" == *.launch.py ]]; then
      LAUNCH_FILE="$LAUNCH_PROFILE"
    else
      echo "[start_web_gui] unknown LAUNCH=$LAUNCH_PROFILE" >&2
      exit 1
    fi
    ;;
esac
echo "[start_web_gui] RMW=$RMW  LAUNCH=$LAUNCH_FILE"

LOG_DIR="$(mktemp -d /tmp/mw_web_gui.XXXXXX)"
echo "[start_web_gui] logs -> $LOG_DIR"

# Preflight: aggressively clean stragglers from previous runs. Matches on
# both process names and bound ports so a half-killed prior session never
# holds onto a resource we need.
for pat in \
  "hfsm_executor" "mw_hfsm_executor" "virtual_robot" \
  "move_motor_server" "capture_image_server" "mw_skill_supervisor" \
  "mw_task_repository" "drive_to_pose_server" \
  "foxglove_bridge" "cloudflared" "dispatch_http" \
  "gz sim" "parameter_bridge" "robot_state_publisher" ; do
  # `-o` pattern matching avoids suiciding: we never match the current
  # script's command line (which contains start_web_gui).
  pkill -9 -f "$pat" 2>/dev/null || true
done
fuser -k "$FG_PORT/tcp" "$VITE_PORT/tcp" "$DISPATCH_PORT/tcp" 1667/tcp 1668/tcp \
  >/dev/null 2>&1 || true
sleep 2

cleanup() {
  echo "[start_web_gui] shutting down ..."
  for var in ROS_LAUNCH_PID VITE_PID DISPATCH_PID TUNNEL_PID ZENOHD_PID; do
    pid="${!var:-}"
    if [[ -n "$pid" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  pkill -9 -f "hfsm_executor|mw_hfsm_executor|foxglove_bridge|virtual_robot|move_motor_server|capture_image_server|mw_skill_supervisor|mw_task_repository|rmw_zenohd" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# If the user selected zenoh, start the router first. Skip if one is
# already running on the default port (7447).
if [[ "$RMW" == "rmw_zenoh_cpp" ]]; then
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":7447$"; then
    echo "[start_web_gui] rmw_zenohd already running on :7447"
  else
    echo "[start_web_gui] launching rmw_zenohd ..."
    ros2 run rmw_zenoh_cpp rmw_zenohd >"$LOG_DIR/zenohd.log" 2>&1 &
    ZENOHD_PID=$!
    echo "[start_web_gui] rmw_zenohd PID=$ZENOHD_PID"
    # Give the router a moment before peers start announcing.
    sleep 2
  fi
fi

# 1. ROS launch
ros2 launch mw_web_gui "$LAUNCH_FILE" foxglove_port:="$FG_PORT" \
  > "$LOG_DIR/ros.log" 2>&1 &
ROS_LAUNCH_PID=$!
echo "[start_web_gui] ros2 launch PID=$ROS_LAUNCH_PID ($LAUNCH_FILE)"

# 2. npm install on first run
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "[start_web_gui] installing npm deps (first run) ..."
  (cd "$FRONTEND_DIR" && npm install) || {
    echo "[start_web_gui] npm install failed" >&2
    exit 1
  }
fi

# 3. Vite dev server
(cd "$FRONTEND_DIR" && npm run dev -- --port "$VITE_PORT") \
  > "$LOG_DIR/vite.log" 2>&1 &
VITE_PID=$!
echo "[start_web_gui] vite PID=$VITE_PID"

# 4. Dispatch HTTP bridge (Python): translates POST /dispatch -> ExecuteSubJob action
cat >"$LOG_DIR/dispatch_http.py" <<'PY'
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from mw_task_msgs.action import ExecuteSubJob
from mw_task_msgs.srv import ListTasks


class DispatchNode(Node):
    def __init__(self) -> None:
        super().__init__('mw_web_dispatch_http')
        self.cli = ActionClient(
            self, ExecuteSubJob, '/mw_task_manager/execute_sub_job')
        self.list_cli = self.create_client(
            ListTasks, '/mw_task_repository/list_tasks')

    def send(self, subjob_id: str,
             behavior_parameter: dict, userdata_in: dict) -> tuple[bool, str]:
        """Fire-and-forget: we ONLY need the action goal to leave the
        wire. Confirmation of acceptance can race with rclcpp_action's
        internal request map on fast loopback (same issue reported in
        memory/technical_gotchas.md), which would spuriously 500 the
        HTTP caller. Observers follow live progress via /mw_hfsm_status,
        so returning as soon as the goal is sent is sufficient."""
        if not self.cli.wait_for_server(timeout_sec=3.0):
            return False, 'action server unavailable'
        goal = ExecuteSubJob.Goal()
        goal.subjob_id = subjob_id
        goal.behavior_parameter_json = json.dumps(behavior_parameter or {})
        goal.userdata_in_json = json.dumps(userdata_in or {})
        self.cli.send_goal_async(goal)
        return True, 'dispatched'

    def list_tasks(self) -> tuple[bool, list, str]:
        """Synchronously hit the repo's list_tasks service. Called from
        the HTTP handler thread; rclpy spin_until_future_complete is
        safe here because the main thread has its own rclpy.spin()."""
        if not self.list_cli.wait_for_service(timeout_sec=3.0):
            return False, [], 'list_tasks service unavailable'
        req = ListTasks.Request()
        fut = self.list_cli.call_async(req)
        # Poll without hijacking the executor (spin_until_future_complete
        # from a non-main thread would clash with the primary spin()).
        deadline = 3.0
        import time as _t
        t0 = _t.monotonic()
        while not fut.done() and (_t.monotonic() - t0) < deadline:
            _t.sleep(0.02)
        if not fut.done():
            return False, [], 'list_tasks timeout'
        resp = fut.result()
        if resp is None:
            return False, [], 'no response'
        return True, list(resp.task_ids), 'ok'


node: DispatchNode | None = None


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/tasks':
            try:
                assert node is not None
                ok, ids, msg = node.list_tasks()
                code = 200 if ok else 500
                self._json(code, {'ok': ok, 'task_ids': ids, 'message': msg})
            except Exception as e:  # noqa: BLE001
                self._json(500, {'error': str(e)})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != '/dispatch':
            self.send_error(404)
            return
        try:
            n = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(n) or b'{}')
            # Accept both legacy 'task_id' and the new 'subjob_id' for
            # backwards-friendliness while the frontend transitions.
            subjob_id = body.get('subjob_id') or body.get('task_id')
            if not subjob_id:
                self._json(400, {'error': 'missing subjob_id'})
                return
            behavior_parameter = body.get('behavior_parameter') or {}
            userdata_in = body.get('userdata_in') or {}
            assert node is not None
            ok, msg = node.send(subjob_id, behavior_parameter, userdata_in)
            self._json(200 if ok else 500, {'ok': ok, 'message': msg})
        except Exception as e:  # noqa: BLE001
            self._json(500, {'error': str(e)})

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, code: int, obj):
        b = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write('[dispatch_http] ' + (format % args) + '\n')


def main():
    global node
    rclpy.init()
    node = DispatchNode()
    port = int(os.environ.get('DISPATCH_PORT', '5174'))
    server = HTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'[dispatch_http] listening on 0.0.0.0:{port}', flush=True)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
PY
DISPATCH_PORT="$DISPATCH_PORT" python3 "$LOG_DIR/dispatch_http.py" \
  > "$LOG_DIR/dispatch.log" 2>&1 &
DISPATCH_PID=$!
echo "[start_web_gui] dispatch http PID=$DISPATCH_PID (port $DISPATCH_PORT)"

# 5. Wait for Vite to be ready before starting the tunnel.
echo "[start_web_gui] waiting for vite :$VITE_PORT ..."
for i in {1..60}; do
  if curl -fs "http://localhost:$VITE_PORT" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# 6. cloudflared quick tunnel (points at vite; inside the page the ws
#    connection falls back to the local hostname — so the tunnel URL is
#    useful for the user-agent, while the backend stays local).
cloudflared tunnel --url "http://localhost:$VITE_PORT" \
  > "$LOG_DIR/tunnel.log" 2>&1 &
TUNNEL_PID=$!

# Print the tunnel URL when it appears.
echo "[start_web_gui] waiting for cloudflared URL ..."
URL=""
for i in {1..60}; do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG_DIR/tunnel.log" | head -1 || true)
  if [[ -n "$URL" ]]; then break; fi
  sleep 1
done

echo ""
echo "============================================================"
if [[ -n "$URL" ]]; then
  echo "  Public URL:  $URL"
  echo "  LAN URL:     http://$(hostname -I | awk '{print $1}'):$VITE_PORT"
  echo ""
  echo "  (Vite proxy forwards /ws -> foxglove_bridge:$FG_PORT and"
  echo "   /api -> dispatch_http:$DISPATCH_PORT on the same origin.)"
else
  echo "  cloudflared did not produce a URL — see $LOG_DIR/tunnel.log"
  echo "  LAN URL: http://$(hostname -I | awk '{print $1}'):$VITE_PORT"
fi
echo "============================================================"
echo ""
echo "  logs: $LOG_DIR"
echo "  press Ctrl-C to stop"
echo ""

wait
