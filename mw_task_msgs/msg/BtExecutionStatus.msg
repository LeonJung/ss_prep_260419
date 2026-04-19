# Real-time BT execution status published by the task_manager.
# Consumed by the web GUI live monitor and any external observer.

string task_id              # id that was dispatched ('' when idle)
string tree_name            # BehaviorTree root ID (from XML)
string tree_xml             # full BT XML text (so frontend can render
                            # the tree without a separate file fetch)
string current_node_name    # most recently ticked leaf's name attribute

uint8 STATUS_IDLE=0
uint8 STATUS_RUNNING=1
uint8 STATUS_SUCCESS=2
uint8 STATUS_FAILURE=3
uint8 status

builtin_interfaces/Time start_time
float64 elapsed_sec
