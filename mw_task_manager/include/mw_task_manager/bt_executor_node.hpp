// Long-lived BT executor.
//
// Exposes the ExecuteTask action: on each goal, load the XML from the
// task repository (via LoadTask service), build a BT, tick at tick_rate_hz
// until it finishes, and report the outcome. /mw_bt_status is published
// throughout so the web GUI and any observer can follow live progress.
#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <string>

#include <behaviortree_cpp/behavior_tree.h>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/groot2_publisher.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include <mw_task_msgs/action/execute_task.hpp>
#include <mw_task_msgs/msg/bt_execution_status.hpp>
#include <mw_task_msgs/srv/load_task.hpp>

namespace mw_task_manager
{

class BtExecutorNode : public rclcpp::Node
{
public:
  using ExecuteTask = mw_task_msgs::action::ExecuteTask;
  using GoalHandle = rclcpp_action::ServerGoalHandle<ExecuteTask>;
  using LoadTask = mw_task_msgs::srv::LoadTask;
  using BtStatus = mw_task_msgs::msg::BtExecutionStatus;

  BtExecutorNode();
  void init();  // call after make_shared (uses shared_from_this)

private:
  rclcpp_action::GoalResponse handleGoal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const ExecuteTask::Goal>);
  rclcpp_action::CancelResponse handleCancel(
    const std::shared_ptr<GoalHandle>);
  void handleAccepted(const std::shared_ptr<GoalHandle>);
  void execute(const std::shared_ptr<GoalHandle>);

  std::string loadXml(const std::string & task_id, std::string & err);
  void publishStatus();

  BT::BehaviorTreeFactory factory_;
  rclcpp::Client<LoadTask>::SharedPtr load_task_client_;
  rclcpp_action::Server<ExecuteTask>::SharedPtr action_server_;
  rclcpp::Publisher<BtStatus>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr status_timer_;
  std::unique_ptr<BT::Groot2Publisher> groot_publisher_;

  double tick_rate_hz_{10.0};
  int groot_port_{1667};

  // State guarded by state_mutex_ so status_timer_ (executor thread) and
  // action execution (detached thread) can safely access concurrently.
  std::mutex state_mutex_;
  std::string current_task_id_;
  std::string current_tree_name_;
  std::string current_tree_xml_;
  std::string current_node_name_;
  uint8_t current_status_{0};      // STATUS_IDLE
  rclcpp::Time start_time_;
};

}  // namespace mw_task_manager
