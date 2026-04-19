#include "mw_task_manager/bt_executor_node.hpp"

#include <chrono>
#include <thread>
#include <utility>

#include "mw_skill_library/skills/capture_image_bt_node.hpp"
#include "mw_skill_library/skills/drive_to_pose_bt_node.hpp"
#include "mw_skill_library/skills/move_motor_bt_node.hpp"
#include "mw_skill_library/skills/navigate_to_pose_bt_node.hpp"

namespace mw_task_manager
{

using namespace std::chrono_literals;

BtExecutorNode::BtExecutorNode()
: rclcpp::Node("mw_bt_executor")
{
  declare_parameter<double>("tick_rate_hz", 10.0);
  declare_parameter<int>("groot_port", 1667);
  declare_parameter<std::string>("load_task_service",
    "/mw_task_repository/load_task");
}

void BtExecutorNode::init()
{
  auto shared = shared_from_this();

  tick_rate_hz_ = get_parameter("tick_rate_hz").as_double();
  groot_port_ = get_parameter("groot_port").as_int();

  // Register skill nodes once; new trees created per-goal reuse the factory.
  factory_.registerNodeType<mw_skill_library::MoveMotorBtNode>(
    "MoveMotor", shared);
  factory_.registerNodeType<mw_skill_library::CaptureImageBtNode>(
    "CaptureImage", shared);
  factory_.registerNodeType<mw_skill_library::NavigateToPoseBtNode>(
    "NavigateToPose", shared);
  factory_.registerNodeType<mw_skill_library::DriveToPoseBtNode>(
    "DriveToPose", shared);

  load_task_client_ = create_client<LoadTask>(
    get_parameter("load_task_service").as_string());

  status_pub_ = create_publisher<BtStatus>("/mw_bt_status", rclcpp::QoS(10));
  status_timer_ = create_wall_timer(
    100ms, std::bind(&BtExecutorNode::publishStatus, this));

  using namespace std::placeholders;
  action_server_ = rclcpp_action::create_server<ExecuteTask>(
    this, "/mw_task_manager/execute_task",
    std::bind(&BtExecutorNode::handleGoal, this, _1, _2),
    std::bind(&BtExecutorNode::handleCancel, this, _1),
    std::bind(&BtExecutorNode::handleAccepted, this, _1));

  RCLCPP_INFO(
    get_logger(),
    "mw_task_manager ready: action=/mw_task_manager/execute_task "
    "tick_hz=%.1f groot_port=%d", tick_rate_hz_, groot_port_);
}

rclcpp_action::GoalResponse BtExecutorNode::handleGoal(
  const rclcpp_action::GoalUUID &,
  std::shared_ptr<const ExecuteTask::Goal> goal)
{
  RCLCPP_INFO(get_logger(), "ExecuteTask goal: task_id='%s'",
              goal->task_id.c_str());
  {
    std::lock_guard<std::mutex> lk(state_mutex_);
    if (current_status_ == BtStatus::STATUS_RUNNING) {
      RCLCPP_WARN(get_logger(), "rejecting goal: already running '%s'",
                  current_task_id_.c_str());
      return rclcpp_action::GoalResponse::REJECT;
    }
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse BtExecutorNode::handleCancel(
  const std::shared_ptr<GoalHandle>)
{
  return rclcpp_action::CancelResponse::ACCEPT;
}

void BtExecutorNode::handleAccepted(const std::shared_ptr<GoalHandle> gh)
{
  std::thread{[this, gh]() { execute(gh); }}.detach();
}

std::string BtExecutorNode::loadXml(
  const std::string & task_id, std::string & err)
{
  if (!load_task_client_->wait_for_service(2s)) {
    err = "load_task service unavailable";
    return {};
  }
  auto req = std::make_shared<LoadTask::Request>();
  req->task_id = task_id;
  auto fut = load_task_client_->async_send_request(req);
  if (fut.wait_for(3s) != std::future_status::ready) {
    err = "load_task timeout";
    return {};
  }
  auto resp = fut.get();
  if (!resp->success) {
    err = "load_task: " + resp->message;
    return {};
  }
  return resp->xml_content;
}

void BtExecutorNode::execute(const std::shared_ptr<GoalHandle> gh)
{
  const auto goal = gh->get_goal();
  auto feedback = std::make_shared<ExecuteTask::Feedback>();
  auto result = std::make_shared<ExecuteTask::Result>();

  std::string err;
  const std::string xml = loadXml(goal->task_id, err);
  if (xml.empty()) {
    result->succeeded = false;
    result->message = err;
    gh->abort(result);
    {
      std::lock_guard<std::mutex> lk(state_mutex_);
      current_status_ = BtStatus::STATUS_FAILURE;
      current_task_id_ = goal->task_id;
    }
    return;
  }

  BT::Tree tree;
  try {
    tree = factory_.createTreeFromText(xml);
  } catch (const std::exception & e) {
    result->succeeded = false;
    result->message = std::string{"BT parse error: "} + e.what();
    gh->abort(result);
    return;
  }

  // Track current ticking leaf for /mw_bt_status by subscribing to
  // per-node status-change events. Subscriptions are held in a local
  // vector whose lifetime matches the tree's execution.
  std::vector<BT::TreeNode::StatusChangeSubscriber> subs;
  auto status_cb = [this](BT::TimePoint /*stamp*/,
                          const BT::TreeNode & node,
                          BT::NodeStatus /*prev*/,
                          BT::NodeStatus status) {
      if (status == BT::NodeStatus::RUNNING) {
        std::lock_guard<std::mutex> lk(state_mutex_);
        current_node_name_ = node.name();
      }
  };
  tree.applyVisitor([&](BT::TreeNode * node) {
      subs.push_back(node->subscribeToStatusChange(status_cb));
  });

  std::string tree_name = tree.subtrees.empty() ?
    std::string{"tree"} : tree.subtrees.front()->tree_ID;

  // Groot2Publisher is optional — the web GUI owns live visualization.
  // If the ZMQ port is stuck (TIME_WAIT from a prior process, etc.) we
  // just skip it rather than bring down the whole task manager.
  try {
    groot_publisher_ =
      std::make_unique<BT::Groot2Publisher>(tree, groot_port_);
  } catch (const std::exception & e) {
    RCLCPP_WARN(
      get_logger(),
      "Groot2Publisher disabled (port %d busy?): %s",
      groot_port_, e.what());
    groot_publisher_.reset();
  }

  {
    std::lock_guard<std::mutex> lk(state_mutex_);
    current_task_id_ = goal->task_id;
    current_tree_name_ = tree_name;
    current_tree_xml_ = xml;
    current_node_name_.clear();
    current_status_ = BtStatus::STATUS_RUNNING;
    start_time_ = now();
  }

  RCLCPP_INFO(get_logger(), "executing '%s' (%s)",
              goal->task_id.c_str(), tree_name.c_str());

  rclcpp::Rate rate(tick_rate_hz_);
  BT::NodeStatus status = BT::NodeStatus::RUNNING;
  while (rclcpp::ok() && status == BT::NodeStatus::RUNNING) {
    if (gh->is_canceling()) {
      tree.haltTree();
      result->succeeded = false;
      result->message = "canceled";
      gh->canceled(result);
      std::lock_guard<std::mutex> lk(state_mutex_);
      current_status_ = BtStatus::STATUS_FAILURE;
      groot_publisher_.reset();
      return;
    }
    status = tree.tickOnce();

    {
      std::lock_guard<std::mutex> lk(state_mutex_);
      feedback->current_node_name = current_node_name_;
      feedback->elapsed_sec = (now() - start_time_).seconds();
    }
    gh->publish_feedback(feedback);
    rate.sleep();
  }

  const bool ok = (status == BT::NodeStatus::SUCCESS);
  result->succeeded = ok;
  result->message = ok ? "ok" : "failed";
  result->tree_name = tree_name;
  if (ok) {
    gh->succeed(result);
    RCLCPP_INFO(get_logger(), "BT '%s' finished: SUCCESS", tree_name.c_str());
  } else {
    gh->abort(result);
    RCLCPP_WARN(get_logger(), "BT '%s' finished: FAILURE", tree_name.c_str());
  }

  {
    std::lock_guard<std::mutex> lk(state_mutex_);
    current_status_ = ok ? BtStatus::STATUS_SUCCESS : BtStatus::STATUS_FAILURE;
    current_node_name_.clear();
  }
  groot_publisher_.reset();
}

void BtExecutorNode::publishStatus()
{
  BtStatus msg;
  {
    std::lock_guard<std::mutex> lk(state_mutex_);
    msg.task_id = current_task_id_;
    msg.tree_name = current_tree_name_;
    msg.tree_xml = current_tree_xml_;
    msg.current_node_name = current_node_name_;
    msg.status = current_status_;
    msg.start_time = start_time_;
    if (current_status_ == BtStatus::STATUS_RUNNING) {
      msg.elapsed_sec = (now() - start_time_).seconds();
    } else {
      msg.elapsed_sec = 0.0;
    }
  }
  status_pub_->publish(msg);
}

}  // namespace mw_task_manager
