#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "nav_msgs/msg/odometry.hpp"

class RobotPoseDisplay : public rclcpp::Node
{
public:
  RobotPoseDisplay()
  : Node("robot_pose_display")
  {
    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      "odom",
      10,
      std::bind(&RobotPoseDisplay::odom_callback, this, std::placeholders::_1));

    RCLCPP_INFO(this->get_logger(), "Robot pose display node started. Subscribing to /odom");
  }

private:
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;

  void odom_callback(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    const auto & position = msg->pose.pose.position;
    RCLCPP_INFO(this->get_logger(), "Robot position: x=%.3f y=%.3f z=%.3f",
                position.x,
                position.y,
                position.z);
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<RobotPoseDisplay>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
