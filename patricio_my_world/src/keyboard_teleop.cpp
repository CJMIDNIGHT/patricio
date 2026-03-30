#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

#include <chrono>
#include <memory>

#include "geometry_msgs/msg/twist.hpp"
#include "rclcpp/rclcpp.hpp"

using namespace std::chrono_literals;

class KeyboardTeleop : public rclcpp::Node
{
public:
  KeyboardTeleop()
  : Node("keyboard_teleop")
  {
    cmd_vel_pub_ = this->create_publisher<geometry_msgs::msg::Twist>("cmd_vel", 10);

    saved_flags_ = fcntl(STDIN_FILENO, F_GETFL, 0);
    tcgetattr(STDIN_FILENO, &saved_term_);

    set_raw_mode();

    current_linear_ = 0.0;
    current_angular_ = 0.0;
    last_key_time_ = this->now();

    timer_ = this->create_wall_timer(
      50ms,
      std::bind(&KeyboardTeleop::timer_callback, this));

    RCLCPP_INFO(this->get_logger(), "Keyboard teleop node started. Use W/A/S/D to move, X to stop, Q to quit.");
  }

  ~KeyboardTeleop()
  {
    restore_terminal();
    RCLCPP_INFO(this->get_logger(), "Keyboard teleop node stopped.");
  }

private:
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  struct termios saved_term_;
  int saved_flags_;
  double current_linear_;
  double current_angular_;
  rclcpp::Time last_key_time_;

  static constexpr double LINEAR_STEP = 0.25;
  static constexpr double ANGULAR_STEP = 0.8;
  static constexpr double KEY_TIMEOUT = 0.25;

  void set_raw_mode()
  {
    struct termios raw = saved_term_;
    raw.c_lflag &= ~(ECHO | ICANON);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &raw);
    fcntl(STDIN_FILENO, F_SETFL, saved_flags_ | O_NONBLOCK);
  }

  void restore_terminal()
  {
    tcsetattr(STDIN_FILENO, TCSANOW, &saved_term_);
    fcntl(STDIN_FILENO, F_SETFL, saved_flags_);
  }

  int read_key()
  {
    unsigned char c;
    ssize_t n = read(STDIN_FILENO, &c, 1);
    if (n <= 0) {
      return -1;
    }
    return static_cast<int>(c);
  }

  void process_key(int c)
  {
    switch (c) {
      case 'w':
      case 'W':
        current_linear_ = LINEAR_STEP;
        current_angular_ = 0.0;
        RCLCPP_INFO(this->get_logger(), "Forward");
        break;
      case 's':
      case 'S':
        current_linear_ = -LINEAR_STEP;
        current_angular_ = 0.0;
        RCLCPP_INFO(this->get_logger(), "Backward");
        break;
      case 'a':
      case 'A':
        current_linear_ = 0.0;
        current_angular_ = ANGULAR_STEP;
        RCLCPP_INFO(this->get_logger(), "Turn left");
        break;
      case 'd':
      case 'D':
        current_linear_ = 0.0;
        current_angular_ = -ANGULAR_STEP;
        RCLCPP_INFO(this->get_logger(), "Turn right");
        break;
      case 'x':
      case 'X':
        current_linear_ = 0.0;
        current_angular_ = 0.0;
        RCLCPP_INFO(this->get_logger(), "Stop");
        break;
      case 'q':
      case 'Q':
        RCLCPP_INFO(this->get_logger(), "Quit requested");
        rclcpp::shutdown();
        break;
      default:
        break;
    }
  }

  void publish_command(double linear, double angular)
  {
    geometry_msgs::msg::Twist twist;
    twist.linear.x = linear;
    twist.angular.z = angular;
    cmd_vel_pub_->publish(twist);
  }

  void timer_callback()
  {
    while (true) {
      int c = read_key();
      if (c < 0) {
        break;
      }
      process_key(c);
    }

    publish_command(current_linear_, current_angular_);
  }
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<KeyboardTeleop>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
