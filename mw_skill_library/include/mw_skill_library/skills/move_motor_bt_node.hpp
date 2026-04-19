#pragma once

#include "mw_skill_library/ros2_action_bt_node.hpp"
#include <mw_task_msgs/action/move_motor.hpp>

namespace mw_skill_library
{

class MoveMotorBtNode : public Ros2ActionBtNode<mw_task_msgs::action::MoveMotor>
{
public:
  using ActionT = mw_task_msgs::action::MoveMotor;

  MoveMotorBtNode(
    const std::string & name,
    const BT::NodeConfig & cfg,
    rclcpp::Node::SharedPtr node)
  : Ros2ActionBtNode<ActionT>(name, cfg, node, "move_motor") {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("motor_id", "motor identifier"),
      BT::InputPort<double>("target_position", "target joint position"),
      BT::InputPort<double>("max_velocity", 1.0, "max velocity (rad/s or m/s)"),
      BT::OutputPort<double>("final_position", "reported final position"),
    };
  }

  ActionT::Goal buildGoal() override
  {
    ActionT::Goal g;
    getInput("motor_id", g.motor_id);
    getInput("target_position", g.target_position);
    getInput("max_velocity", g.max_velocity);
    return g;
  }

  void onFinalResult(const ActionT::Result & r,
                     rclcpp_action::ResultCode /*code*/) override
  {
    setOutput("final_position", r.final_position);
  }
};

}  // namespace mw_skill_library
