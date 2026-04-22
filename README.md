# mw robot Task Manager — ROS 2 Jazzy source tree

This repo holds the `src/` tree of a colcon workspace implementing a
robot-side Task Manager on a self-built **Hierarchical FSM** engine.
The design models tasks as `SubJob → Step → SubStep` (robot-side layers;
`Work` and `Job` concepts live upstream in MCS/RCS, on other PCs).  The
guiding rule is *every layer is one invocation; iteration of children
is the parent's responsibility* — no layer self-iterates.

## Packages

| package | role |
|---|---|
| `mw_task_msgs` | msg / srv / action definitions (`ExecuteSubJob`, `HfsmExecutionStatus`, skill actions) |
| `mw_hfsm_engine` | pure-Python HFSM runtime: `State` / `StateMachine` / `BehaviorSM`, `Parallel`, `RetryDecorator`, `@register_state` registry, JSON/dict `build_from_spec` loader |
| `mw_hfsm_ros` | ROS 2 bridge: `LifecycleAwareActionState` base that calls a LifecycleNode action with lifecycle probing + recovery |
| `mw_skill_library` | driver-level LifecycleNode action servers (`move_motor`, `capture_image`, `drive_to_pose` — a self-contained P-controller, no nav2) |
| `mw_skill_states` | concrete HFSM `State` wrappers around each skill action (`DriveToPoseState`, `MoveMotorState`, `CaptureImageState`) |
| `mw_hfsm_examples` | reference SubJobs (e.g. `VisitThreePoints`) wiring skill states into a full `BehaviorSM` |
| `mw_task_manager` | `hfsm_executor` node: serves `ExecuteSubJob` action, publishes `/mw_hfsm_status` (with live `spec_json` + `active_state`), honors goal-cancel via the engine's `CancelToken` |
| `mw_task_repository` | Git-backed spec CRUD (stores our JSON HFSM spec) + dispatch CLI |
| `mw_skill_supervisor` | lifecycle watchdog that auto-configures + activates managed skill servers |
| `mw_robot_emulator` | virtual robot with motor physics + fault injection (`/virtual_robot/inject_fault`) |
| `mw_web_gui` | Vue 3 + VueFlow live monitor (`HfsmStateView`, `HfsmStatus`) + dispatch UI + cloudflared tunnel wrapper |
| `mw_rcs_bridge` | Phase 5 stub: VDA5050-inspired REST bridge from a remote RCS to the local executor |
| `mw_bringup` | launch files (emulator, navigate_test, demo) |

## Layer → package mapping

```
SubJob   →  BehaviorSM  (mw_hfsm_engine)
Step     →  StateMachine (mw_hfsm_engine)         ← internals may use Parallel / Retry
SubStep  →  State (mw_hfsm_engine)
              └─ LifecycleAwareActionState  (mw_hfsm_ros)
                    └─ concrete: DriveToPoseState / MoveMotorState / ...  (mw_skill_states)
                          └─ ROS 2 action server (mw_skill_library)   ← the actual driver
```

## Place in a workspace

```bash
mkdir -p ~/mw_ws && cd ~/mw_ws
git clone git@github.com:LeonJung/ss_prep_260419.git src
```

## Build / run

```bash
source /opt/ros/jazzy/setup.bash
colcon build
source install/setup.bash
export MW_WS=$PWD
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp   # or rmw_zenoh_cpp

# Emulator-based web GUI stack:
bash src/mw_web_gui/scripts/start_web_gui.sh

# TurtleBot3 Gazebo navigation demo:
export TURTLEBOT3_MODEL=waffle
export LAUNCH=navigate
bash src/mw_web_gui/scripts/start_web_gui.sh
```

The web stack exposes Vite (5173), dispatch HTTP (5174), and
foxglove_bridge (8765); `start_web_gui.sh` prints a
`https://*.trycloudflare.com` URL for remote access.

## Test

```bash
colcon test --packages-select \
  mw_hfsm_engine mw_hfsm_ros mw_task_manager \
  mw_skill_states mw_hfsm_examples mw_rcs_bridge
```

All unit tests run without a live ROS graph (action / lifecycle clients
are mocked at the wrapper layer).

## Status

- Engine core (State / StateMachine / BehaviorSM / Parallel / Retry / Registry / spec loader) ✅
- ROS 2 integration (LifecycleAwareActionState) ✅
- Concrete SubSteps (DriveToPoseState / MoveMotorState / CaptureImageState) ✅
- HFSM executor node (`hfsm_executor` in mw_task_manager) ✅
- Web GUI topic / component migration to `/mw_hfsm_status` + `HfsmStateView` ✅
- Executor-side spec serializer (publishes live `spec_json` + `active_state` on `/mw_hfsm_status`) ✅
- Cooperative cancellation (CancelToken threaded through engine, Parallel region bail-out, LifecycleAwareActionState wait-loop polling, executor cancel_callback) ✅
- Reference SubJob (`VisitThreePoints` in `mw_hfsm_examples`) ✅
- RCS bridge Phase 5 stub (REST endpoints: `POST /order`, `POST /cancel`, `GET /state`) ✅
- Author-facing JSON/YAML SubJob editor — pending

Detailed design rationale (BT vs HFSM analysis, scenario walkthroughs,
layer / iteration rules) lives in the private plan file at
`~/.claude/plans/floating-petting-charm.md`.
