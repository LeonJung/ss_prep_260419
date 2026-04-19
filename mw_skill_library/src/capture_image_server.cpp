// CaptureImage SubStep action server — Phase 3 LifecycleNode.
#include <chrono>
#include <memory>
#include <string>
#include <thread>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include <mw_task_msgs/action/capture_image.hpp>
#include <mw_task_msgs/srv/request_capture.hpp>

using CaptureImage = mw_task_msgs::action::CaptureImage;
using GoalHandle = rclcpp_action::ServerGoalHandle<CaptureImage>;
using RequestCapture = mw_task_msgs::srv::RequestCapture;
using CallbackReturn =
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

class CaptureImageServer : public rclcpp_lifecycle::LifecycleNode
{
public:
  CaptureImageServer()
  : rclcpp_lifecycle::LifecycleNode("capture_image_server")
  {
    RCLCPP_INFO(get_logger(), "capture_image_server constructed (unconfigured)");
  }

  CallbackReturn on_configure(const rclcpp_lifecycle::State &) override
  {
    capture_client_ =
      create_client<RequestCapture>("/virtual_robot/capture_image");
    RCLCPP_INFO(get_logger(), "on_configure: client ready");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_activate(const rclcpp_lifecycle::State &) override
  {
    using namespace std::placeholders;
    action_server_ = rclcpp_action::create_server<CaptureImage>(
      get_node_base_interface(),
      get_node_clock_interface(),
      get_node_logging_interface(),
      get_node_waitables_interface(),
      "capture_image",
      std::bind(&CaptureImageServer::handleGoal, this, _1, _2),
      std::bind(&CaptureImageServer::handleCancel, this, _1),
      std::bind(&CaptureImageServer::handleAccepted, this, _1));
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
    capture_client_.reset();
    RCLCPP_INFO(get_logger(), "on_cleanup: client released");
    return CallbackReturn::SUCCESS;
  }

  CallbackReturn on_shutdown(const rclcpp_lifecycle::State &) override
  {
    action_server_.reset();
    capture_client_.reset();
    return CallbackReturn::SUCCESS;
  }

private:
  rclcpp_action::Server<CaptureImage>::SharedPtr action_server_;
  rclcpp::Client<RequestCapture>::SharedPtr capture_client_;

  rclcpp_action::GoalResponse handleGoal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const CaptureImage::Goal> goal)
  {
    RCLCPP_INFO(
      get_logger(), "accept: camera=%s save_path=%s",
      goal->camera_id.c_str(), goal->save_path.c_str());
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

  void execute(const std::shared_ptr<GoalHandle> gh)
  {
    const auto goal = gh->get_goal();
    auto result = std::make_shared<CaptureImage::Result>();

    if (!capture_client_ ||
        !capture_client_->wait_for_service(std::chrono::seconds(2)))
    {
      result->succeeded = false;
      result->message = "emulator capture service unavailable";
      gh->abort(result);
      RCLCPP_ERROR(get_logger(), "[%s] %s",
                   goal->camera_id.c_str(), result->message.c_str());
      return;
    }

    auto req = std::make_shared<RequestCapture::Request>();
    req->camera_id = goal->camera_id;
    req->save_path = goal->save_path;
    auto future = capture_client_->async_send_request(req);
    if (future.wait_for(std::chrono::seconds(5)) !=
      std::future_status::ready)
    {
      result->succeeded = false;
      result->message = "capture timed out";
      gh->abort(result);
      RCLCPP_ERROR(get_logger(), "[%s] timeout", goal->camera_id.c_str());
      return;
    }
    auto resp = future.get();
    result->succeeded = resp->success;
    result->image_path = resp->image_path;
    result->message = resp->message;
    if (resp->success) {
      gh->succeed(result);
      RCLCPP_INFO(get_logger(), "[%s] captured -> %s",
                  goal->camera_id.c_str(), resp->image_path.c_str());
    } else {
      gh->abort(result);
      RCLCPP_ERROR(get_logger(), "[%s] capture failed: %s",
                   goal->camera_id.c_str(), resp->message.c_str());
    }
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<CaptureImageServer>();
  rclcpp::executors::SingleThreadedExecutor exec;
  exec.add_node(node->get_node_base_interface());
  exec.spin();
  rclcpp::shutdown();
  return 0;
}
