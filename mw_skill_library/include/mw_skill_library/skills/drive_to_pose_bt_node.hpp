// BT leaf wrapping the DriveToPose action (our own odom-frame P-controller,
// NOT nav2). This is the canonical "Step 제어 template" requested by the
// user: a thin BT leaf that maps BT ports -> action goal fields, lets the
// action server own all the control loop details.
#pragma once

#include "mw_skill_library/ros2_action_bt_node.hpp"

#include <mw_task_msgs/action/drive_to_pose.hpp>

namespace mw_skill_library
{

class DriveToPoseBtNode :
  public Ros2ActionBtNode<mw_task_msgs::action::DriveToPose>
{
public:
  using ActionT = mw_task_msgs::action::DriveToPose;

  DriveToPoseBtNode(
    const std::string & name,
    const BT::NodeConfig & cfg,
    rclcpp::Node::SharedPtr node)
  : Ros2ActionBtNode<ActionT>(name, cfg, node, "drive_to_pose")
  {
    goal_timeout_sec_ = 90.0;
    server_wait_timeout_sec_ = 10.0;
  }

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<double>("target_x", "target x in odom frame (m)"),
      BT::InputPort<double>("target_y", "target y in odom frame (m)"),
      BT::InputPort<double>("target_yaw", 0.0, "target yaw (rad)"),
      BT::InputPort<double>("xy_tolerance", 0.15, "xy tolerance (m)"),
      BT::InputPort<double>("yaw_tolerance", 0.1, "yaw tolerance (rad)"),
    };
  }

  ActionT::Goal buildGoal() override
  {
    ActionT::Goal g;
    getInput("target_x", g.target_x);
    getInput("target_y", g.target_y);
    getInput("target_yaw", g.target_yaw);
    getInput("xy_tolerance", g.xy_tolerance);
    getInput("yaw_tolerance", g.yaw_tolerance);
    return g;
  }
};

}  // namespace mw_skill_library
