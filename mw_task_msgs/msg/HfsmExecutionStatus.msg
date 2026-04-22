# Real-time HFSM execution status published by the task_manager.
# Consumed by the web GUI live monitor and any external observer.

string subjob_id            # id of the SubJob currently running ('' when idle)
string spec_json            # full HFSM spec JSON (serialized tree of SubJob/Step/SubStep)
                            # so the frontend can render the chart without a separate fetch
string active_state         # dot-separated path of the active state,
                            # e.g. "VisitThreePoints.GO_P2.Drive"
string userdata_snapshot_json   # JSON-serialized userdata dict at the last transition

uint8 STATUS_IDLE=0
uint8 STATUS_RUNNING=1
uint8 STATUS_SUCCESS=2
uint8 STATUS_FAILURE=3
uint8 status

builtin_interfaces/Time start_time
float64 elapsed_sec
