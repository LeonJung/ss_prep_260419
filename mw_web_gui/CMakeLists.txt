cmake_minimum_required(VERSION 3.8)
project(mw_web_gui)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch scripts DESTINATION share/${PROJECT_NAME})
install(PROGRAMS
  scripts/start_web_gui.sh
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
