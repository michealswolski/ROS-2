"""Convert a drive log CSV into a rosbag2 bag using the MCAP storage plugin.

Each signal becomes a std_msgs/msg/Float64 topic (/vehicle/rpm,
/vehicle/speed, /vehicle/pressure) and every message is written with the
logger's original timestamp, so `ros2 bag play` reproduces the drive timing.
"""

import argparse
import os
import shutil

import rosbag2_py
from rclpy.serialization import serialize_message
from std_msgs.msg import Float64

from .drive_log import DEFAULT_START_EPOCH_S, MSG_TYPE, SIGNALS, read_drive_csv


def write_bag(series, out_dir: str, storage_preset: str = '') -> int:
    writer = rosbag2_py.SequentialWriter()
    writer.open(
        rosbag2_py.StorageOptions(uri=out_dir, storage_id='mcap',
                                  storage_preset_profile=storage_preset),
        rosbag2_py.ConverterOptions(input_serialization_format='cdr',
                                    output_serialization_format='cdr'))
    for i, sig in enumerate(SIGNALS):
        writer.create_topic(rosbag2_py.TopicMetadata(
            id=i, name=sig.topic, type=MSG_TYPE, serialization_format='cdr'))

    # Merge all signals into one time-ordered stream.
    events = sorted(
        (t, sig.topic, v)
        for sig in SIGNALS
        for t, v in zip(series[sig.key].times_ns, series[sig.key].values))
    msg = Float64()
    for t, topic, v in events:
        msg.data = v
        writer.write(topic, serialize_message(msg), t)
    del writer  # closes the bag and writes metadata.yaml
    return len(events)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('csv', help='drive log CSV')
    p.add_argument('-o', '--output', default='bags/sample_drive', help='bag directory to create')
    p.add_argument('--time-col', default='timestamp_s',
                   help='time column: seconds, relative or Unix epoch')
    for sig in SIGNALS:
        p.add_argument(f'--{sig.key}-col', default=sig.column,
                       help=f'CSV column for {sig.topic} [{sig.unit}]')
    p.add_argument('--start-epoch', type=float, default=DEFAULT_START_EPOCH_S,
                   help='epoch seconds to anchor relative timestamps')
    p.add_argument('--zstd', action='store_true', help='MCAP chunk compression (zstd_fast preset)')
    p.add_argument('-f', '--force', action='store_true', help='overwrite an existing bag')
    args = p.parse_args(argv)

    if os.path.exists(args.output):
        if not args.force:
            p.error(f'{args.output} exists (use --force to overwrite)')
        shutil.rmtree(args.output)

    columns = {sig.key: getattr(args, f'{sig.key}_col') for sig in SIGNALS}
    series = read_drive_csv(args.csv, args.time_col, columns, args.start_epoch)
    n = write_bag(series, args.output, 'zstd_fast' if args.zstd else '')
    counts = ', '.join(f'{s.topic}={len(series[s.key])}' for s in SIGNALS)
    print(f'wrote {n} messages to {args.output} (mcap): {counts}')


if __name__ == '__main__':
    main()
