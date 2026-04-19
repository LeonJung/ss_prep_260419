// BT leaf wrapping nav2_msgs::action::NavigateToPose.
// Demonstrates the "Step = BT subtree, SubStep = ROS 2 action wrapper"
// pattern for navigation-family skills, using nav2 as the lower-level
// motion planner/controller. The pattern generalizes: other manipulation
// / perception Steps should mirror this shape (inherit Ros2ActionBtNode<T>,
// implement providedPorts + buildGoal, optional onFinalResult/onFeedback).
#pragma once

#include <cmath>

#include "mw_skill_library/ros2_action_bt_node.hpp"

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <nav2_msgs/action/navigate_to_pose.hpp>

namespace mw_skill_library
{

class NavigateToPoseBtNode :
  public Ros2ActionBtNode<nav2_msgs::action::NavigateToPose>
{
public:
  using ActionT = nav2_msgs::action::NavigateToPose;

  NavigateToPoseBtNode(
    const std::string & name,
    const BT::NodeConfig & cfg,
    rclcpp::Node::SharedPtr node)
  : Ros2ActionBtNode<ActionT>(name, cfg, node, "navigate_to_pose")
  {
    // Nav2 navigations can be long (tens of seconds) on a 3x3 sandbox;
    // override the default 40s goal timeout for this skill.
    goal_timeout_sec_ = 120.0;
    server_wait_timeout_sec_ = 15.0;
  }

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<double>("x", "target x in frame (m)"),
      BT::InputPort<double>("y", "target y in frame (m)"),
      BT::InputPort<double>("yaw", 0.0, "target yaw (rad)"),
      BT::InputPort<std::string>("frame", "map", "target pose frame_id"),
    };
  }

  ActionT::Goal buildGoal() override
  {
    ActionT::Goal g;
    double x = 0.0;
    double y = 0.0;
    double yaw = 0.0;
    std::string frame = "map";
    getInput("x", x);
    getInput("y", y);
    getInput("yaw", yaw);
    getInput("frame", frame);

    g.pose.header.frame_id = frame;
    g.pose.header.stamp = node_->now();
    g.pose.pose.position.x = x;
    g.pose.pose.position.y = y;
    g.pose.pose.position.z = 0.0;
    g.pose.pose.orientation.x = 0.0;
    g.pose.pose.orientation.y = 0.0;
    g.pose.pose.orientation.z = std::sin(yaw * 0.5);
    g.pose.pose.orientation.w = std::cos(yaw * 0.5);
    return g;
  }
};

}  // namespace mw_skill_library
