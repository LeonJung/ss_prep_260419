// Minimal BT.CPP v4 leaf wrapper over rclcpp_action::Client.
// Phase 1: plain action client + non-blocking polling + cancel on halt.
// Phase 3 will derive a LifecycleAware variant that queries skill lifecycle
// state before sending a goal and coordinates with mw_skill_supervisor.
#pragma once

#include <atomic>
#include <chrono>
#include <memory>
#include <string>

#include <behaviortree_cpp/action_node.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

namespace mw_skill_library
{

template <typename ActionT>
class Ros2ActionBtNode : public BT::StatefulActionNode
{
public:
  using Goal = typename ActionT::Goal;
  using Result = typename ActionT::Result;
  using Feedback = typename ActionT::Feedback;
  using Client = rclcpp_action::Client<ActionT>;
  using GoalHandle = rclcpp_action::ClientGoalHandle<ActionT>;
  using SendGoalOpts = typename Client::SendGoalOptions;

  Ros2ActionBtNode(
    const std::string & name,
    const BT::NodeConfig & cfg,
    rclcpp::Node::SharedPtr node,
    const std::string & action_name)
  : BT::StatefulActionNode(name, cfg),
    node_(std::move(node)),
    action_name_(action_name)
  {
    client_ = rclcpp_action::create_client<ActionT>(node_, action_name_);
  }

  virtual Goal buildGoal() = 0;
  virtual void onFinalResult(const Result &, rclcpp_action::ResultCode) {}
  virtual void onFeedback(const Feedback &) {}

protected:
  BT::NodeStatus onStart() override
  {
    start_time_ = node_->now();
    goal_sent_ = false;
    result_received_ = false;
    goal_handle_.reset();
    return trySend();
  }

  BT::NodeStatus onRunning() override
  {
    if (!goal_sent_) {
      auto s = trySend();
      if (s != BT::NodeStatus::RUNNING) {
        return s;
      }
    }
    if (result_received_) {
      onFinalResult(last_result_, last_result_code_);
      return (last_result_code_ == rclcpp_action::ResultCode::SUCCEEDED)
               ? BT::NodeStatus::SUCCESS
               : BT::NodeStatus::FAILURE;
    }
    // Guard against a skill server that dies mid-goal: if no result
    // callback arrives within goal_timeout_sec_, give up so the BT can
    // react (recovery subtree, abort, etc.). Without this, onRunning()
    // would loop forever and the BT would hang.
    if ((node_->now() - start_time_).seconds() > goal_timeout_sec_) {
      RCLCPP_ERROR(
        node_->get_logger(),
        "[%s] goal timeout (%.1fs) on '%s' — no result received",
        this->name().c_str(), goal_timeout_sec_, action_name_.c_str());
      if (goal_handle_) {
        client_->async_cancel_goal(goal_handle_);
      }
      return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override
  {
    if (goal_handle_) {
      client_->async_cancel_goal(goal_handle_);
    }
  }

  BT::NodeStatus trySend()
  {
    if (!client_->action_server_is_ready()) {
      const double waited = (node_->now() - start_time_).seconds();
      if (waited > server_wait_timeout_sec_) {
        RCLCPP_ERROR(
          node_->get_logger(),
          "[%s] action server '%s' unavailable after %.1fs",
          this->name().c_str(), action_name_.c_str(), waited);
        return BT::NodeStatus::FAILURE;
      }
      return BT::NodeStatus::RUNNING;
    }

    SendGoalOpts opts;
    opts.goal_response_callback =
      [this](typename GoalHandle::SharedPtr h) { goal_handle_ = h; };
    opts.feedback_callback =
      [this](typename GoalHandle::SharedPtr,
             const std::shared_ptr<const Feedback> fb) { onFeedback(*fb); };
    opts.result_callback =
      [this](const typename GoalHandle::WrappedResult & r) {
        last_result_ = *r.result;
        last_result_code_ = r.code;
        result_received_ = true;
        RCLCPP_INFO(
          node_->get_logger(),
          "[%s] result_callback fired, code=%d",
          this->name().c_str(), static_cast<int>(r.code));
      };

    client_->async_send_goal(buildGoal(), opts);
    goal_sent_ = true;
    RCLCPP_INFO(
      node_->get_logger(), "[%s] goal dispatched to '%s'",
      this->name().c_str(), action_name_.c_str());
    return BT::NodeStatus::RUNNING;
  }

  rclcpp::Node::SharedPtr node_;
  std::string action_name_;
  typename Client::SharedPtr client_;
  typename GoalHandle::SharedPtr goal_handle_;
  rclcpp::Time start_time_;
  double server_wait_timeout_sec_{5.0};
  // Overall per-goal timeout, covers both discovery and execution. For
  // long-running motion plans, subclasses can raise this in constructor.
  double goal_timeout_sec_{40.0};

  std::atomic<bool> goal_sent_{false};
  std::atomic<bool> result_received_{false};
  Result last_result_;
  rclcpp_action::ResultCode last_result_code_{rclcpp_action::ResultCode::UNKNOWN};
};

}  // namespace mw_skill_library
