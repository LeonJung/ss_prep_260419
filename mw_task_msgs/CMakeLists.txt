cmake_minimum_required(VERSION 3.8)
project(mw_task_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(action_msgs REQUIRED)

find_package(builtin_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/MoveMotor.action"
  "action/CaptureImage.action"
  "action/DriveToPose.action"
  "action/ExecuteSubJob.action"
  "msg/HfsmExecutionStatus.msg"
  "msg/MotorStatus.msg"
  "msg/MotorStatusArray.msg"
  "srv/ListTasks.srv"
  "srv/LoadTask.srv"
  "srv/SaveTask.srv"
  "srv/SetMotorTarget.srv"
  "srv/RequestCapture.srv"
  "srv/InjectFault.srv"
  "srv/ResetRobot.srv"
  DEPENDENCIES std_msgs action_msgs builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
