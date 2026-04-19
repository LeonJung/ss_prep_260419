# mw robot Task Manager — ROS 2 Jazzy source tree

This repo holds the `src/` tree of a colcon workspace exploring a
`SubStep → Step → SubJob → Job` task hierarchy. Primary orchestrator is
BT.CPP v4; an HFSMBTH (FlexBE + BT hybrid) variant is under evaluation.

## Packages

| package | purpose |
|---|---|
| `mw_task_msgs` | msg / srv / action definitions |
| `mw_skill_library` | SubStep action servers (LifecycleNode) + BT leaf wrappers + P-controller `drive_to_pose_server` |
| `mw_task_manager` | long-lived BT.CPP v4 executor exposing `ExecuteTask` action + `/mw_bt_status` |
| `mw_task_repository` | Git-backed Task XML CRUD + dispatch CLI |
| `mw_robot_emulator` | virtual robot with motor physics + fault injection + `/virtual_robot/inject_fault` service |
| `mw_skill_supervisor` | lifecycle watchdog (auto-configure + activate skills) |
| `mw_web_gui` | Vue 3 + VueFlow live monitor + dispatch UI + cloudflared tunnel wrapper |
| `mw_bringup` | launch files + self_test harness |

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

Stack exposes: Vite (5173), dispatch HTTP (5174), foxglove_bridge (8765).
`start_web_gui.sh` prints a `https://*.trycloudflare.com` URL for remote access.

## Status

- Phase 1 — BT executor + dummy skills ✅
- Phase 2 — Task repository + CLI ✅
- Phase 2.5 — Virtual robot emulator ✅
- Phase 3 — 3-layer Lifecycle Management + chaos test ✅
- Phase 4 — Vue 3 Web GUI + cloudflared remote access ✅
- Phase 5 — RCS bridge stub (pending)
- Phase 6 — BT vs FlexBE (HFSMBTH) comparison — design discussion in progress

Detailed design rationale and BT-vs-FlexBE analysis live in the private plan
file at `~/.claude/plans/floating-petting-charm.md`.
