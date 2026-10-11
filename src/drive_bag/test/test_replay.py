"""End-to-end: `ros2 launch drive_bag replay.launch.py` (ros2 bag play + kpi_monitor)."""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytest.importorskip('rosbag2_py')


def _package_installed():
    try:
        from ament_index_python.packages import get_package_share_directory
        get_package_share_directory('drive_bag')
        return shutil.which('ros2') is not None
    except Exception:
        return False


@pytest.mark.skipif(not _package_installed(), reason='drive_bag not installed / ros2 CLI missing')
def test_replay_delivers_every_message(tmp_path):
    from drive_bag.bag_reader import topic_counts
    from drive_bag.csv_to_bag import write_bag
    from drive_bag.drive_log import read_drive_csv
    from drive_bag.generate_sample import generate

    csv_path = tmp_path / 'drive.csv'
    generate(str(csv_path))
    bag = tmp_path / 'bag'
    write_bag(read_drive_csv(str(csv_path)), str(bag))
    out = tmp_path / 'replay.json'

    env = dict(os.environ, ROS_DOMAIN_ID=str(40 + os.getpid() % 50))  # isolate from other runs
    proc = subprocess.run(
        ['ros2', 'launch', 'drive_bag', 'replay.launch.py',
         f'bag:={bag}', 'rate:=20.0', f'output:={out}'],
        env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]

    live = json.loads(out.read_text())
    expected = topic_counts(str(bag))
    assert live['received_messages'] == sum(expected.values())
    assert live['dropped_in_replay'] == 0
    assert live['max_rpm'] == max(read_drive_csv(str(csv_path))['rpm'].values)
