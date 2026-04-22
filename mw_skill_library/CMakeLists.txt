cmake_minimum_required(VERSION 3.14)
project(mw_skill_library)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(lifecycle_msgs REQUIRED)
find_package(mw_task_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)

# ---- Action servers (executables) ----
add_executable(move_motor_server src/move_motor_server.cpp)
ament_target_dependencies(move_motor_server
  rclcpp rclcpp_action rclcpp_lifecycle lifecycle_msgs mw_task_msgs)

add_executable(capture_image_server src/capture_image_server.cpp)
ament_target_dependencies(capture_image_server
  rclcpp rclcpp_action rclcpp_lifecycle lifecycle_msgs mw_task_msgs)

add_executable(drive_to_pose_server src/drive_to_pose_server.cpp)
ament_target_dependencies(drive_to_pose_server
  rclcpp rclcpp_action mw_task_msgs geometry_msgs nav_msgs)

install(TARGETS move_motor_server capture_image_server drive_to_pose_server
  DESTINATION lib/${PROJECT_NAME})

ament_export_dependencies(
  rclcpp rclcpp_action rclcpp_lifecycle lifecycle_msgs
  mw_task_msgs geometry_msgs nav_msgs)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
