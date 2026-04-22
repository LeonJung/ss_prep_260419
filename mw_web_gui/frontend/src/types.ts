// Mirror of mw_task_msgs types — kept as TS interfaces so we can
// serialize/deserialize over the foxglove_bridge JSON channel without
// an autogen pipeline.

export interface HfsmExecutionStatus {
  subjob_id: string;
  spec_json: string;          // full HFSM spec JSON (empty until spec loader lands)
  active_state: string;       // dot-separated path, e.g. "VisitThreePoints.GO_P2.Drive"
  userdata_snapshot_json: string;
  status: number;             // 0 idle, 1 running, 2 success, 3 failure
  start_time: { sec: number; nanosec: number };
  elapsed_sec: number;
}

export interface JointState {
  header: { stamp: { sec: number; nanosec: number }; frame_id: string };
  name: string[];
  position: number[];
  velocity: number[];
  effort: number[];
}

export interface Odometry {
  header: { stamp: { sec: number; nanosec: number }; frame_id: string };
  pose: {
    pose: {
      position: { x: number; y: number; z: number };
      orientation: { x: number; y: number; z: number; w: number };
    };
  };
  twist: {
    twist: {
      linear: { x: number; y: number; z: number };
      angular: { x: number; y: number; z: number };
    };
  };
}

export const HFSM_STATUS_LABELS = [
  'IDLE',
  'RUNNING',
  'SUCCESS',
  'FAILURE',
] as const;
