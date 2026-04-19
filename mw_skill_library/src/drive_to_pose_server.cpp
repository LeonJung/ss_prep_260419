// DriveToPose SubStep action server.
// Template-worthy "Step 제어" example: direct /cmd_vel + /odom closed-loop
// navigation to a 2D (x, y, yaw) target in odom frame. No nav2, no
// global planner — the entire motion is owned by THIS SubStep. Future
// Steps for manipulation / docking / etc. can mirror this shape:
//   1) subscribe to the relevant state topic
//   2) publish the relevant command topic
//   3) run a simple control loop with explicit phases
//   4) expose SUCCESS/FAILURE via the action contract
//
// Phases:
//   ROTATE_TO_HEADING  — in-place yaw to face (target_x, target_y)
//   DRIVE_TO_POINT     — forward motion with heading correction until
//                        Euclidean distance < xy_tolerance
//   ROTATE_TO_YAW      — in-place yaw to match target_yaw
//   DONE               — publish zero twist, succeed()
#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include <geometry_msgs/msg/twist.hpp>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

#include <mw_task_msgs/action/drive_to_pose.hpp>

using DriveToPose = mw_task_msgs::action::DriveToPose;
using GoalHandle = rclcpp_action::ServerGoalHandle<DriveToPose>;
using Twist = geometry_msgs::msg::Twist;
using TwistStamped = geometry_msgs::msg::TwistStamped;
using Odometry = nav_msgs::msg::Odometry;

namespace
{

double normalizeAngle(double a)
{
  while (a > M_PI) {a -= 2.0 * M_PI;}
  while (a < -M_PI) {a += 2.0 * M_PI;}
  return a;
}

double yawFromQuat(double x, double y, double z, double w)
{
  const double siny_cosp = 2.0 * (w * z + x * y);
  const double cosy_cosp = 1.0 - 2.0 * (y * y + z * z);
  return std::atan2(siny_cosp, cosy_cosp);
}

}  // namespace

class DriveToPoseServer : public rclcpp::Node
{
public:
  DriveToPoseServer()
  : rclcpp::Node("drive_to_pose_server")
  {
    using namespace std::placeholders;
    declare_parameter<std::string>("cmd_vel_topic", "/cmd_vel");
    declare_parameter<std::string>("odom_topic", "/odom");
    // TB3 Jazzy / Gazebo Harmonic publishes /cmd_vel as TwistStamped,
    // Humble/Foxy used Twist. We ship both by default and auto-match;
    // to force one, set this param to "twist" or "twist_stamped".
    declare_parameter<std::string>("cmd_vel_format", "both");

    const auto cmd_vel = get_parameter("cmd_vel_topic").as_string();
    const auto odom = get_parameter("odom_topic").as_string();
    const auto fmt = get_parameter("cmd_vel_format").as_string();

    if (fmt != "twist_stamped") {
      cmd_pub_ = create_publisher<Twist>(cmd_vel, 10);
    }
    if (fmt != "twist") {
      cmd_stamped_pub_ = create_publisher<TwistStamped>(cmd_vel, 10);
    }
    odom_sub_ = create_subscription<Odometry>(
      odom, 10,
      std::bind(&DriveToPoseServer::onOdom, this, _1));
    action_server_ = rclcpp_action::create_server<DriveToPose>(
      this, "drive_to_pose",
      std::bind(&DriveToPoseServer::handleGoal, this, _1, _2),
      std::bind(&DriveToPoseServer::handleCancel, this, _1),
      std::bind(&DriveToPoseServer::handleAccepted, this, _1));
    RCLCPP_INFO(
      get_logger(),
      "drive_to_pose server ready (cmd=%s fmt=%s, odom=%s)",
      cmd_vel.c_str(), fmt.c_str(), odom.c_str());
  }

private:
  rclcpp_action::Server<DriveToPose>::SharedPtr action_server_;
  rclcpp::Publisher<Twist>::SharedPtr cmd_pub_;
  rclcpp::Publisher<TwistStamped>::SharedPtr cmd_stamped_pub_;
  rclcpp::Subscription<Odometry>::SharedPtr odom_sub_;

  std::mutex pose_mutex_;
  bool pose_valid_{false};
  double cur_x_{0.0};
  double cur_y_{0.0};
  double cur_yaw_{0.0};

  void onOdom(const Odometry::SharedPtr msg)
  {
    const auto & o = msg->pose.pose.orientation;
    const double yaw = yawFromQuat(o.x, o.y, o.z, o.w);
    std::lock_guard<std::mutex> lk(pose_mutex_);
    cur_x_ = msg->pose.pose.position.x;
    cur_y_ = msg->pose.pose.position.y;
    cur_yaw_ = yaw;
    pose_valid_ = true;
  }

  bool snapshot(double & x, double & y, double & yaw)
  {
    std::lock_guard<std::mutex> lk(pose_mutex_);
    if (!pose_valid_) {
      return false;
    }
    x = cur_x_;
    y = cur_y_;
    yaw = cur_yaw_;
    return true;
  }

  void publishStop()
  {
    publishCmd(Twist{});
  }

  void publishCmd(const Twist & t)
  {
    if (cmd_pub_) {
      cmd_pub_->publish(t);
    }
    if (cmd_stamped_pub_) {
      TwistStamped ts;
      ts.header.stamp = now();
      ts.header.frame_id = "base_link";
      ts.twist = t;
      cmd_stamped_pub_->publish(ts);
    }
  }

  rclcpp_action::GoalResponse handleGoal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const DriveToPose::Goal> goal)
  {
    RCLCPP_INFO(
      get_logger(), "accept: target=(%.2f, %.2f, %.2f)",
      goal->target_x, goal->target_y, goal->target_yaw);
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handleCancel(const std::shared_ptr<GoalHandle>)
  {
    publishStop();
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handleAccepted(const std::shared_ptr<GoalHandle> gh)
  {
    std::thread{[this, gh]() { execute(gh); }}.detach();
  }

  void execute(const std::shared_ptr<GoalHandle> gh)
  {
    const auto goal = gh->get_goal();
    auto feedback = std::make_shared<DriveToPose::Feedback>();
    auto result = std::make_shared<DriveToPose::Result>();

    const double vmax = std::max(0.01, goal->max_linear_velocity);
    const double wmax = std::max(0.1, goal->max_angular_velocity);
    const double xy_tol = std::max(1e-3, goal->xy_tolerance);
    const double yaw_tol = std::max(1e-3, goal->yaw_tolerance);

    // Wait for first odom.
    const auto wait_deadline = now() + rclcpp::Duration::from_seconds(5.0);
    while (rclcpp::ok() && now() < wait_deadline) {
      double dx, dy, dyaw;
      if (snapshot(dx, dy, dyaw)) {break;}
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    if (!pose_valid_) {
      result->succeeded = false;
      result->message = "no odom received";
      gh->abort(result);
      RCLCPP_ERROR(get_logger(), "no odom in 5s — aborting");
      return;
    }

    enum Phase { ROTATE_TO_HEADING, DRIVE_TO_POINT, ROTATE_TO_YAW };
    Phase phase = ROTATE_TO_HEADING;

    const auto start_time = now();
    const double overall_timeout = 60.0;
    rclcpp::Rate rate(20.0);
    Twist cmd;

    while (rclcpp::ok()) {
      if (gh->is_canceling()) {
        publishStop();
        result->succeeded = false;
        result->message = "canceled";
        gh->canceled(result);
        return;
      }
      if ((now() - start_time).seconds() > overall_timeout) {
        publishStop();
        result->succeeded = false;
        result->message = "overall timeout";
        gh->abort(result);
        RCLCPP_ERROR(get_logger(), "timeout after %.1fs", overall_timeout);
        return;
      }

      double x, y, yaw;
      if (!snapshot(x, y, yaw)) {rate.sleep(); continue;}

      const double dx = goal->target_x - x;
      const double dy = goal->target_y - y;
      const double dist = std::hypot(dx, dy);
      const double heading = std::atan2(dy, dx);

      cmd = Twist{};  // zero by default

      switch (phase) {
        case ROTATE_TO_HEADING: {
          if (dist < xy_tol) {
            // Already on target point, skip to final yaw.
            phase = ROTATE_TO_YAW;
            break;
          }
          const double err = normalizeAngle(heading - yaw);
          if (std::abs(err) < 0.08) {
            phase = DRIVE_TO_POINT;
            break;
          }
          cmd.angular.z = std::clamp(2.0 * err, -wmax, wmax);
          break;
        }
        case DRIVE_TO_POINT: {
          if (dist < xy_tol) {
            phase = ROTATE_TO_YAW;
            break;
          }
          const double err = normalizeAngle(heading - yaw);
          // Blend: forward scales with dist, correct heading via yaw rate.
          cmd.linear.x = std::clamp(0.8 * dist, 0.05, vmax);
          cmd.angular.z = std::clamp(1.5 * err, -wmax, wmax);
          break;
        }
        case ROTATE_TO_YAW: {
          const double err = normalizeAngle(goal->target_yaw - yaw);
          if (std::abs(err) < yaw_tol) {
            publishStop();
            result->final_x = x;
            result->final_y = y;
            result->final_yaw = yaw;
            result->succeeded = true;
            result->message = "arrived";
            gh->succeed(result);
            RCLCPP_INFO(
              get_logger(), "arrived at (%.2f, %.2f, %.2f)",
              x, y, yaw);
            return;
          }
          cmd.angular.z = std::clamp(2.0 * err, -wmax, wmax);
          break;
        }
      }

      publishCmd(cmd);

      feedback->current_x = x;
      feedback->current_y = y;
      feedback->current_yaw = yaw;
      feedback->distance_remaining = dist;
      gh->publish_feedback(feedback);

      rate.sleep();
    }
    publishStop();
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<DriveToPoseServer>());
  rclcpp::shutdown();
  return 0;
}
