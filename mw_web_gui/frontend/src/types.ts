// Mirror of mw_task_msgs types — kept as TS interfaces so we can
// serialize/deserialize over the foxglove_bridge JSON channel without
// an autogen pipeline.

export interface BtExecutionStatus {
  task_id: string;
  tree_name: string;
  tree_xml: string;
  current_node_name: string;
  status: number; // 0 idle, 1 running, 2 success, 3 failure
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

export const BT_STATUS_LABELS = [
  'IDLE',
  'RUNNING',
  'SUCCESS',
  'FAILURE',
] as const;
