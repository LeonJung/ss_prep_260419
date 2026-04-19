#!/usr/bin/env python3
"""End-to-end self-test for Phase 2.5.

Launches the emulator stack (virtual_robot + skill servers + repo_node),
then sequentially runs three scenarios:
  1. normal          — dispatch fetch_cup, expect BT SUCCESS
  2. stuck motor     — inject fault on base_x, dispatch, expect BT FAILURE
  3. recovery        — clear fault, dispatch, expect BT SUCCESS

Designed to be run from a built workspace:
  source install/setup.bash
  python3 src/mw_bringup/scripts/self_test.py
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEMO_XML = ROOT / 'install' / 'mw_task_manager' / 'share' / \
    'mw_task_manager' / 'config' / 'demo_fetch_cup.xml'


def run(cmd, **kw):
    return subprocess.run(cmd, check=False, **kw)


def wait_for_service(name: str, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(
            ['ros2', 'service', 'list'],
            capture_output=True, text=True)
        if name in r.stdout:
            return True
        time.sleep(0.5)
    return False


def save_fetch_cup() -> None:
    xml = DEMO_XML.read_text(encoding='utf-8')
    esc = xml.replace('"', '\\"').replace('\n', '\\n')
    cmd = [
        'ros2', 'service', 'call',
        '/mw_task_repository/save_task',
        'mw_task_msgs/srv/SaveTask',
        f'{{task_id: "fetch_cup", xml_content: "{esc}", commit_message: "self_test"}}',
    ]
    r = run(cmd, capture_output=True, text=True, timeout=10)
    if 'success=True' not in r.stdout:
        raise RuntimeError(f'save_task failed: {r.stdout}')


def inject_fault(target: str, kind: str, parameter: float = 0.0) -> None:
    cmd = [
        'ros2', 'service', 'call',
        '/virtual_robot/inject_fault',
        'mw_task_msgs/srv/InjectFault',
        f'{{target: "{target}", kind: "{kind}", parameter: {parameter}}}',
    ]
    r = run(cmd, capture_output=True, text=True, timeout=10)
    print(f'[inject_fault {target} {kind}] -> {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)"}')
    if 'applied=True' not in r.stdout:
        raise RuntimeError(f'inject_fault failed: {r.stdout}')


def reset_robot() -> None:
    cmd = [
        'ros2', 'service', 'call',
        '/virtual_robot/reset',
        'mw_task_msgs/srv/ResetRobot',
        '{}',
    ]
    r = run(cmd, capture_output=True, text=True, timeout=10)
    print(f'[reset_robot] -> {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)"}')
    if 'success=True' not in r.stdout:
        raise RuntimeError(f'reset failed: {r.stdout}')


_BT_RESULT_RE = re.compile(r'BT finished: (SUCCESS|FAILURE)')


def dispatch_and_wait(task_id: str, timeout_sec: float = 30.0) -> str:
    """Run dispatch CLI and parse its launch output for BT result."""
    cmd = ['ros2', 'run', 'mw_task_repository', 'dispatch', task_id]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=os.environ.copy(), preexec_fn=os.setsid)
    deadline = time.time() + timeout_sec
    result = None
    try:
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            sys.stdout.write(line)
            m = _BT_RESULT_RE.search(line)
            if m:
                result = m.group(1)
                break
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()
    if result is None:
        raise RuntimeError(f'dispatch did not report BT finish within {timeout_sec}s')
    return result


def _preflight_cleanup() -> None:
    """Kill stragglers from previous (possibly interrupted) runs."""
    patterns = [
        'move_motor_server', 'capture_image_server', 'virtual_robot',
        'mw_task_repository', 'mw_skill_supervisor',
        'mw_task_manager_node', 'ros2 launch mw_bringup',
    ]
    for pat in patterns:
        subprocess.run(['pkill', '-9', '-f', pat],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)


def main() -> int:
    os.environ['RMW_IMPLEMENTATION'] = 'rmw_fastrtps_cpp'
    repo_dir = tempfile.mkdtemp(prefix='mw_tasks_st_')
    os.environ['MW_TASK_REPO_DIR'] = repo_dir

    _preflight_cleanup()
    launch_log = open('/tmp/mw_self_test_launch.log', 'w')
    launch = subprocess.Popen(
        ['ros2', 'launch', 'mw_bringup', 'emulator.launch.py'],
        stdout=launch_log, stderr=subprocess.STDOUT,
        env=os.environ.copy(), preexec_fn=os.setsid)

    failures = []
    try:
        print('[self-test] waiting for emulator services ...')
        if not wait_for_service('/virtual_robot/set_motor_target'):
            raise RuntimeError('virtual_robot services did not appear in time')
        if not wait_for_service('/mw_task_repository/save_task'):
            raise RuntimeError('repo services did not appear in time')
        time.sleep(1.0)  # let discovery settle

        print('[self-test] saving fetch_cup to repository ...')
        save_fetch_cup()

        # --- Scenario 1: normal ---
        print('\n[self-test] === 1/3 NORMAL ===')
        reset_robot()
        r = dispatch_and_wait('fetch_cup')
        print(f'  result: BT {r}')
        if r != 'SUCCESS':
            failures.append(f'normal: expected SUCCESS got {r}')

        # --- Scenario 2: stuck motor ---
        print('\n[self-test] === 2/3 STUCK MOTOR (base_x) ===')
        reset_robot()
        inject_fault('motor:base_x', 'stuck')
        r = dispatch_and_wait('fetch_cup', timeout_sec=30)
        print(f'  result: BT {r}')
        if r != 'FAILURE':
            failures.append(f'stuck: expected FAILURE got {r}')

        # --- Scenario 3: recovery ---
        print('\n[self-test] === 3/4 RECOVERY (clear fault) ===')
        reset_robot()
        r = dispatch_and_wait('fetch_cup')
        print(f'  result: BT {r}')
        if r != 'SUCCESS':
            failures.append(f'recovery: expected SUCCESS got {r}')

        # --- Scenario 4: chaos — kill -9 a skill server, expect
        #     Layer 1 respawn + Layer 3 supervisor auto-activation so
        #     the NEXT dispatch still succeeds end-to-end. ---
        print('\n[self-test] === 4/4 CHAOS (kill -9 move_motor_server) ===')
        reset_robot()
        victim = subprocess.run(
            ['pgrep', '-f', 'move_motor_server'],
            capture_output=True, text=True)
        pids = [int(p) for p in victim.stdout.split() if p.strip().isdigit()]
        if not pids:
            failures.append('chaos: no move_motor_server to kill')
        else:
            print(f'  [chaos] killing move_motor_server pids={pids}')
            for pid in pids:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass
            # Allow Layer 1 respawn (respawn_delay=2.0) + Layer 3
            # supervisor poll (2 Hz) to drive the fresh unconfigured
            # node back to ACTIVE. Empirically <8s in a clean CI.
            print('  [chaos] waiting 10s for respawn + auto-activation ...')
            time.sleep(10.0)
            r = dispatch_and_wait('fetch_cup')
            print(f'  result: BT {r}')
            if r != 'SUCCESS':
                failures.append(f'chaos-recovery: expected SUCCESS got {r}')

    except Exception as e:  # noqa: BLE001
        failures.append(f'harness error: {e}')
    finally:
        print('\n[self-test] tearing down emulator stack ...')
        try:
            os.killpg(os.getpgid(launch.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            launch.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(launch.pid), signal.SIGKILL)
            launch.wait()
        launch_log.close()

    print('\n[self-test] ====== SUMMARY ======')
    if failures:
        for f in failures:
            print(f'  FAIL: {f}')
        return 1
    print('  all scenarios passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
