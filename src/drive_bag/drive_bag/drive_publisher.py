"""ROS 2 node: publish a drive log CSV live as /vehicle/rpm, /vehicle/speed, /vehicle/pressure.

This is the "live logger" path: run it alongside
`ros2 bag record -s mcap /vehicle/rpm /vehicle/speed /vehicle/pressure`
to record a bag the same way you would from a real vehicle.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64

from .drive_log import SIGNALS, read_drive_csv


class DrivePublisher(Node):
    def __init__(self):
        super().__init__('drive_publisher')
        csv_path = self.declare_parameter('csv', 'data/sample_drive.csv').value
        self.rate = float(self.declare_parameter('rate', 1.0).value)

        series = read_drive_csv(csv_path)
        self.events = sorted(
            (t, sig.topic, v)
            for sig in SIGNALS
            for t, v in zip(series[sig.key].times_ns, series[sig.key].values))
        self.t0_log = self.events[0][0]
        self.pubs = {sig.topic: self.create_publisher(Float64, sig.topic, 100) for sig in SIGNALS}
        self.idx = 0
        self.t0_wall = None
        self.done = False
        self.create_timer(0.005, self._tick)
        self.get_logger().info(f'publishing {len(self.events)} messages from {csv_path} at {self.rate}x')

    def _tick(self):
        now = self.get_clock().now().nanoseconds
        if self.t0_wall is None:
            self.t0_wall = now
        log_now = self.t0_log + (now - self.t0_wall) * self.rate
        while self.idx < len(self.events) and self.events[self.idx][0] <= log_now:
            _, topic, v = self.events[self.idx]
            self.pubs[topic].publish(Float64(data=v))
            self.idx += 1
        if self.idx >= len(self.events):
            self.get_logger().info('end of drive log')
            self.done = True


def main(args=None):
    rclpy.init(args=args)
    node = DrivePublisher()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
