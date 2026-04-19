#include <memory>

#include <rclcpp/rclcpp.hpp>

#include "mw_task_manager/bt_executor_node.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<mw_task_manager::BtExecutorNode>();
  node->init();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
