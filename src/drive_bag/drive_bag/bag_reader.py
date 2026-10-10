"""Read the vehicle topics back out of a rosbag2 bag."""

from typing import Dict

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

from .drive_log import SIGNAL_BY_TOPIC, SIGNALS, Series


def detect_storage_id(bag_dir: str) -> str:
    return rosbag2_py.Info().read_metadata(bag_dir, '').storage_identifier


def read_bag(bag_dir: str) -> Dict[str, Series]:
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=detect_storage_id(bag_dir)),
        rosbag2_py.ConverterOptions('cdr', 'cdr'))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    reader.set_filter(rosbag2_py.StorageFilter(topics=[s.topic for s in SIGNALS]))

    series = {s.key: Series() for s in SIGNALS}
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        msg = deserialize_message(data, types[topic])
        series[SIGNAL_BY_TOPIC[topic].key].append(t_ns, float(msg.data))
    return series


def topic_counts(bag_dir: str) -> Dict[str, int]:
    meta = rosbag2_py.Info().read_metadata(bag_dir, '')
    return {t.topic_metadata.name: t.message_count for t in meta.topics_with_message_count}
