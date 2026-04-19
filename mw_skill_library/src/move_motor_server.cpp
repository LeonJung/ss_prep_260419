// MoveMotor SubStep action server — Phase 3 LifecycleNode.
// Layer 2 of the 3-layer resilience plan (see docs/lifecycle).
//
// Lifecycle contract:
//   unconfigured -> on_configure   : create service client & status subscription
//   inactive     -> on_activate    : create action server (goals accepted)
//   active       -> on_deactivate  : tear down action server (goals rejected)
//   inactive     -> on_cleanup     : tear down client & subscription
//
// When supervised by mw_skill_supervisor, the server is auto-transitioned
// to ACTIVE shortly after launch, and re-transitioned after respawn.
#include <chrono>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include <mw_task_msgs/action/move_motor.hpp>
#include <mw_task_msgs/msg/motor_status.hpp>
#include <mw_task_msgs/msg/motor_status_array.hpp>
#include <mw_task_msgs/srv/set_motor_target.hpp>

using MoveMotor = mw_task_msgs::action::MoveMotor;
using GoalHandle = rclcpp_action::ServerGoalHandle<MoveMotor>;
using SetMotorTarget = mw_task_msgs::srv::SetMotorTarget;
using MotorStatus = mw_task_msgs::msg::MotorStatus;
using MotorStatusArray = mw_task_msgs::msg::MotorStatusArray;
using CallbackReturn =
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

class MoveMotorServer : public rclcpp_lifecycle::LifecycleNode
{
public:
  MoveMotorServer()
  : rclcpp_lifecycle::LifecycleNode("move_motor_server")
  {
    RCLCPP_INFO(get_logger(), "move_motor_server constructed (unconfigured)");
  }

  CallbackReturn on_configure(const rclcpp_lifecycle::State &) override
  {
    set_target_client_ =
      create_client<SetMotorTarget>("/virtual_robot/set_motor_target");
    status_sub_ = create_subscription<MotorStatusArray>(
      "/virtual_robot/motor_status", 10,
      std::bind(&MoveMotorServer::onStatus, this, std::placeholders::_1));
    RCLCPP_INFO(get_logger(), "on_configure: client + subscription ready");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_activate(const rclcpp_lifecycle::State &) override
  {
    using namespace std::placeholders;
    action_server_ = rclcpp_action::create_server<MoveMotor>(
      get_node_base_interface(),
      get_node_clock_interface(),
      get_node_logging_interface(),
      get_node_waitables_interface(),
      "move_motor",
      std::bind(&MoveMotorServer::handleGoal, this, _1, _2),
      std::bind(&MoveMotorServer::handleCancel, this, _1),
      std::bind(&MoveMotorServer::handleAccepted, this, _1));
    RCLCPP_INFO(get_logger(), "on_activate: action server accepting goals");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_deactivate(const rclcpp_lifecycle::State &) override
  {
    action_server_.reset();
    RCLCPP_INFO(get_logger(), "on_deactivate: action server torn down");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_cleanup(const rclcpp_lifecycle::State &) override
  {
    set_target_client_.reset();
    status_sub_.reset();
    {
      std::lock_guard<std::mutex> lk(status_mutex_);
      latest_.clear();
    }
    RCLCPP_INFO(get_logger(), "on_cleanup: client + subscription released");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_shutdown(const rclcpp_lifecycle::State &) override
  {
    action_server_.reset();
    set_target_client_.reset();
    status_sub_.reset();
    return CallbackReturn::SUCCESS;
  }

private:
  rclcpp_action::Server<MoveMotor>::SharedPtr action_server_;
  rclcpp::Client<SetMotorTarget>::SharedPtr set_target_client_;
  rclcpp::Subscription<MotorStatusArray>::SharedPtr status_sub_;

  std::mutex status_mutex_;
  std::unordered_map<std::string, MotorStatus> latest_;

  void onStatus(const MotorStatusArray::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lk(status_mutex_);
    for (const auto & m : msg->motors) {
      latest_[m.motor_id] = m;
    }
  }

  bool tryGetStatus(const std::string & motor_id, MotorStatus & out)
  {
    std::lock_guard<std::mutex> lk(status_mutex_);
    auto it = latest_.find(motor_id);
    if (it == latest_.end()) {
      return false;
    }
    out = it->second;
    return true;
  }

  rclcpp_action::GoalResponse handleGoal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const MoveMotor::Goal> goal)
  {
    RCLCPP_INFO(
      get_logger(), "accept: motor=%s target=%.3f max_vel=%.3f",
      goal->motor_id.c_str(), goal->target_position, goal->max_velocity);
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handleCancel(const std::shared_ptr<GoalHandle>)
  {
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handleAccepted(const std::shared_ptr<GoalHandle> gh)
  {
    std::thread{[this, gh]() { execute(gh); }}.detach();
  }

  bool commitTarget(const MoveMotor::Goal & goal, std::string & err_out)
  {
    if (!set_target_client_ ||
        !set_target_client_->wait_for_service(std::chrono::seconds(2)))
    {
      err_out = "emulator set_motor_target service unavailable";
      return false;
    }
    auto req = std::make_shared<SetMotorTarget::Request>();
    req->motor_id = goal.motor_id;
    req->target_position = goal.target_position;
    req->max_velocity = goal.max_velocity;
    auto future = set_target_client_->async_send_request(req);
    if (future.wait_for(std::chrono::seconds(2)) !=
      std::future_status::ready)
    {
      err_out = "set_motor_target timed out";
      return false;
    }
    auto resp = future.get();
    if (!resp->accepted) {
      err_out = "emulator rejected target: " + resp->message;
      return false;
    }
    return true;
  }

  void execute(const std::shared_ptr<GoalHandle> gh)
  {
    const auto goal = gh->get_goal();
    auto feedback = std::make_shared<MoveMotor::Feedback>();
    auto result = std::make_shared<MoveMotor::Result>();

    std::string err;
    if (!commitTarget(*goal, err)) {
      result->succeeded = false;
      result->message = err;
      gh->abort(result);
      RCLCPP_ERROR(get_logger(), "[%s] %s",
                   goal->motor_id.c_str(), err.c_str());
      return;
    }

    constexpr double tolerance = 5e-3;
    constexpr double overall_timeout_sec = 30.0;
    const auto start = now();
    rclcpp::Rate rate(20.0);

    while (rclcpp::ok()) {
      if (gh->is_canceling()) {
        result->succeeded = false;
        result->message = "canceled";
        gh->canceled(result);
        return;
      }
      if ((now() - start).seconds() > overall_timeout_sec) {
        result->succeeded = false;
        result->message = "timeout waiting for motor to reach target";
        gh->abort(result);
        RCLCPP_ERROR(get_logger(), "[%s] timeout", goal->motor_id.c_str());
        return;
      }
      MotorStatus st;
      if (tryGetStatus(goal->motor_id, st)) {
        if (st.status == MotorStatus::STATUS_DEAD ||
            st.status == MotorStatus::STATUS_UNREACHABLE)
        {
          result->succeeded = false;
          result->final_position = st.position;
          result->message = "motor in fault state";
          gh->abort(result);
          RCLCPP_ERROR(get_logger(), "[%s] fault status=%u",
                       goal->motor_id.c_str(), st.status);
          return;
        }
        const double err_abs =
          std::abs(st.position - goal->target_position);
        feedback->current_position = st.position;
        feedback->progress =
          goal->target_position == 0.0 ? 1.0 :
          std::max(0.0, 1.0 - err_abs / std::abs(goal->target_position));
        gh->publish_feedback(feedback);

        if (st.status == MotorStatus::STATUS_STUCK) {
          if ((now() - start).seconds() > 2.0 && err_abs > tolerance) {
            result->succeeded = false;
            result->final_position = st.position;
            result->message = "motor stuck";
            gh->abort(result);
            RCLCPP_ERROR(get_logger(), "[%s] stuck at %.3f",
                         goal->motor_id.c_str(), st.position);
            return;
          }
        }
        if (err_abs <= tolerance) {
          result->succeeded = true;
          result->final_position = st.position;
          result->message = "ok";
          gh->succeed(result);
          RCLCPP_INFO(get_logger(), "[%s] reached %.3f",
                      goal->motor_id.c_str(), st.position);
          return;
        }
      }
      rate.sleep();
    }
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MoveMotorServer>();
  rclcpp::executors::SingleThreadedExecutor exec;
  exec.add_node(node->get_node_base_interface());
  exec.spin();
  rclcpp::shutdown();
  return 0;
}
