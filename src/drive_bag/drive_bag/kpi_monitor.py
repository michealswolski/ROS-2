"""ROS 2 node: compute drive KPIs live while `ros2 bag play` replays a drive.

Subscribes to /vehicle/rpm, /vehicle/speed and /vehicle/pressure, publishes
a running KPI summary as JSON on /drive_kpis, and when the replay goes quiet
prints a final report. If the `bag` parameter is set, the per-topic message
counts in the bag's metadata are compared with what actually arrived, which
gives the messages dropped during replay.
"""

import json
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float64, String

from .drive_log import SIGNALS


class TopicStats:
    def __init__(self):
        self.count = 0
        self.total = 0.0
        self.min = math.inf
        self.max = -math.inf

    def add(self, v: float) -> None:
        self.count += 1
        self.total += v
        self.min = min(self.min, v)
        self.max = max(self.max, v)

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else float('nan')


class KpiMonitor(Node):
    def __init__(self):
        super().__init__('kpi_monitor')
        self.bag = self.declare_parameter('bag', '').value
        self.output = self.declare_parameter('output', '').value
        self.idle_timeout_s = self.declare_parameter('idle_timeout_s', 3.0).value
        report_period_s = self.declare_parameter('report_period_s', 1.0).value

        self.expected = {}
        if self.bag:
            from .bag_reader import topic_counts
            self.expected = topic_counts(self.bag)
            self.get_logger().info(
                f'expecting {sum(self.expected.values())} messages from {self.bag}')

        self.stats = {s.key: TopicStats() for s in SIGNALS}
        self.first_rx = None
        self.last_rx = None
        self.done = False

        qos = QoSProfile(depth=1000, reliability=ReliabilityPolicy.RELIABLE)
        for sig in SIGNALS:
            self.create_subscription(
                Float64, sig.topic, lambda msg, k=sig.key: self._on_msg(k, msg), qos)
        self.pub = self.create_publisher(String, '/drive_kpis', 10)
        self.create_timer(report_period_s, self._on_timer)
        self.get_logger().info('waiting for /vehicle/* messages (start `ros2 bag play`)')

    def _now_s(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def _on_msg(self, key: str, msg: Float64) -> None:
        now = self._now_s()
        if self.first_rx is None:
            self.first_rx = now
        self.last_rx = now
        self.stats[key].add(msg.data)

    def summary(self) -> dict:
        rpm, speed, pressure = (self.stats[k] for k in ('rpm', 'speed', 'pressure'))
        signals = {}
        for sig in SIGNALS:
            st = self.stats[sig.key]
            entry = {'received': st.count}
            if sig.topic in self.expected:
                entry['in_bag'] = self.expected[sig.topic]
                entry['dropped_in_replay'] = max(self.expected[sig.topic] - st.count, 0)
            signals[sig.key] = entry
        out = {
            'max_rpm': round(rpm.max, 1) if rpm.count else None,
            'avg_speed_kph': round(speed.mean, 2) if speed.count else None,
            'max_speed_kph': round(speed.max, 2) if speed.count else None,
            'min_pressure_kpa': round(pressure.min, 1) if pressure.count else None,
            'max_pressure_kpa': round(pressure.max, 1) if pressure.count else None,
            'received_messages': sum(s.count for s in self.stats.values()),
            'replay_wall_time_s': round(self.last_rx - self.first_rx, 2) if self.first_rx else 0.0,
            'signals': signals,
        }
        if self.expected:
            out['dropped_in_replay'] = sum(s.get('dropped_in_replay', 0) for s in signals.values())
        return out

    def _on_timer(self) -> None:
        if self.first_rx is None:
            return
        s = self.summary()
        self.pub.publish(String(data=json.dumps(s)))
        self.get_logger().info(
            f"rx={s['received_messages']} max_rpm={s['max_rpm']} "
            f"avg_speed={s['avg_speed_kph']} km/h")
        if self.idle_timeout_s > 0 and self._now_s() - self.last_rx > self.idle_timeout_s:
            self.finish()

    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        s = self.summary()
        lines = ['replay finished -- live KPIs',
                 f"  max RPM            : {s['max_rpm']}",
                 f"  average speed      : {s['avg_speed_kph']} km/h",
                 f"  pressure min / max : {s['min_pressure_kpa']} / {s['max_pressure_kpa']} kPa",
                 f"  messages received  : {s['received_messages']}"]
        if 'dropped_in_replay' in s:
            lines.append(f"  dropped in replay  : {s['dropped_in_replay']}")
        for k, v in s['signals'].items():
            lines.append(f'    {k:<9} {v}')
        self.get_logger().info('\n'.join(lines))
        if self.output:
            with open(self.output, 'w') as f:
                json.dump(s, f, indent=2)
                f.write('\n')
            self.get_logger().info(f'wrote {self.output}')


def main(args=None):
    rclpy.init(args=args)
    node = KpiMonitor()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        node.finish()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
