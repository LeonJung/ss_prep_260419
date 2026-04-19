#pragma once

#include "mw_skill_library/ros2_action_bt_node.hpp"
#include <mw_task_msgs/action/capture_image.hpp>

namespace mw_skill_library
{

class CaptureImageBtNode : public Ros2ActionBtNode<mw_task_msgs::action::CaptureImage>
{
public:
  using ActionT = mw_task_msgs::action::CaptureImage;

  CaptureImageBtNode(
    const std::string & name,
    const BT::NodeConfig & cfg,
    rclcpp::Node::SharedPtr node)
  : Ros2ActionBtNode<ActionT>(name, cfg, node, "capture_image") {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("camera_id", "camera identifier"),
      BT::InputPort<std::string>("save_path", "filesystem path to save image"),
      BT::OutputPort<std::string>("image_path", "actual saved image path"),
    };
  }

  ActionT::Goal buildGoal() override
  {
    ActionT::Goal g;
    getInput("camera_id", g.camera_id);
    getInput("save_path", g.save_path);
    return g;
  }

  void onFinalResult(const ActionT::Result & r,
                     rclcpp_action::ResultCode /*code*/) override
  {
    setOutput("image_path", r.image_path);
  }
};

}  // namespace mw_skill_library
