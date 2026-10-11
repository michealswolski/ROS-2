"""Convert a non-ROS MCAP drive log (JSON or Protobuf channels) into a rosbag2 bag.

Many loggers (Foxglove SDK, custom CAN loggers) write MCAP whose channels
are JSON or Protobuf rather than ROS 2 CDR, so `ros2 bag play` cannot replay
them directly. This tool picks the RPM, speed and pressure fields out of
those channels and writes a standard rosbag2 bag (storage: mcap) with the
same /vehicle/* topics as csv_to_bag, keeping each message's log time.

Field specs are TOPIC:FIELD.PATH, e.g. --rpm /engine:rpm or
--speed /can/vehicle:wheel.speed_kph (list items: path.0.value).
"""

import argparse
import json
import os
import shutil
from typing import Dict, Tuple

from .drive_log import Series, SIGNALS

DEFAULT_FIELDS = {
    'rpm': '/engine:rpm',
    'speed': '/vehicle:speed_kph',
    'pressure': '/engine:oil_pressure_kpa',
}


def parse_field_spec(spec: str) -> Tuple[str, Tuple[str, ...]]:
    topic, sep, path = spec.rpartition(':')
    if not sep or not topic or not path:
        raise ValueError(f'bad field spec {spec!r}; expected TOPIC:FIELD.PATH')
    return topic, tuple(path.split('.'))


def extract(obj, path: Tuple[str, ...]):
    """Follow a dotted path through dicts, lists and Protobuf messages."""
    for part in path:
        if isinstance(obj, dict):
            obj = obj[part]
        elif part.isdigit() and not hasattr(obj, 'DESCRIPTOR'):
            obj = obj[int(part)]  # list or repeated Protobuf field
        else:
            obj = getattr(obj, part)
    return obj


def protobuf_decoder(schema):
    """Build a Protobuf parser from the FileDescriptorSet embedded in an MCAP schema."""
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

    files = {fd.name: fd for fd in descriptor_pb2.FileDescriptorSet.FromString(schema.data).file}
    pool = descriptor_pool.DescriptorPool()

    def add(name):  # dependencies must be added first
        fd = files.pop(name, None)
        if fd is not None:
            for dep in fd.dependency:
                add(dep)
            pool.Add(fd)

    for name in list(files):
        add(name)
    desc = pool.FindMessageTypeByName(schema.name)
    if hasattr(message_factory, 'GetMessageClass'):  # protobuf >= 4.22
        cls = message_factory.GetMessageClass(desc)
    else:
        cls = message_factory.MessageFactory(pool).GetPrototype(desc)
    return cls.FromString


class _Decoders:
    """Turns raw MCAP message bytes into dicts / message objects per encoding."""

    def __init__(self):
        self._cache = {}

    def decode(self, schema, channel, data: bytes):
        enc = channel.message_encoding
        if enc == 'json':
            return json.loads(data)
        if enc == 'protobuf':
            if schema.id not in self._cache:
                self._cache[schema.id] = protobuf_decoder(schema)
            return self._cache[schema.id](data)
        if enc == 'cdr':
            raise ValueError(
                f'{channel.topic} is already ROS 2 (cdr): this MCAP can be played directly '
                f'(run `ros2 bag reindex <dir> -s mcap` if it has no metadata.yaml)')
        raise ValueError(f'{channel.topic}: unsupported message encoding {enc!r}')


def read_mcap(path: str, fields: Dict[str, str],
              scale: Dict[str, float] = None) -> Dict[str, Series]:
    from mcap.reader import make_reader

    scale = scale or {}
    specs = {key: parse_field_spec(spec) for key, spec in fields.items()}
    by_topic: Dict[str, list] = {}
    for key, (topic, fpath) in specs.items():
        by_topic.setdefault(topic, []).append((key, fpath))

    series = {s.key: Series() for s in SIGNALS}
    decoders = _Decoders()
    seen_topics = set()
    with open(path, 'rb') as f:
        reader = make_reader(f)
        messages = reader.iter_messages(topics=list(by_topic), log_time_order=True)
        for schema, channel, message in messages:
            seen_topics.add(channel.topic)
            msg = decoders.decode(schema, channel, message.data)
            for key, fpath in by_topic[channel.topic]:
                try:
                    value = extract(msg, fpath)
                except (KeyError, IndexError, AttributeError, ValueError):
                    continue  # field absent in this message = missed sample
                if value is None:
                    continue
                series[key].append(message.log_time, float(value) * scale.get(key, 1.0))

    missing = sorted(set(by_topic) - seen_topics)
    if missing:
        raise ValueError(f'{path}: no messages on topic(s) {missing}')
    return series


def main(argv=None):
    from .csv_to_bag import write_bag

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog='\n'.join(__doc__.splitlines()[2:]))
    p.add_argument('mcap', help='input .mcap file (JSON or Protobuf channels)')
    p.add_argument('-o', '--output', required=True, help='bag directory to create')
    for sig in SIGNALS:
        p.add_argument(f'--{sig.key}', default=DEFAULT_FIELDS[sig.key], metavar='TOPIC:FIELD',
                       help=f'source field for {sig.topic} [{sig.unit}] '
                            f'(default {DEFAULT_FIELDS[sig.key]})')
    p.add_argument('--scale', action='append', default=[], metavar='SIGNAL=FACTOR',
                   help='multiply a signal, e.g. --scale speed=3.6 for m/s -> km/h')
    p.add_argument('--zstd', action='store_true', help='MCAP chunk compression (zstd_fast preset)')
    p.add_argument('-f', '--force', action='store_true', help='overwrite an existing bag')
    args = p.parse_args(argv)

    scale = {}
    for item in args.scale:
        key, _, factor = item.partition('=')
        if key not in DEFAULT_FIELDS or not factor:
            p.error(f'bad --scale {item!r}; expected one of {list(DEFAULT_FIELDS)}=FACTOR')
        scale[key] = float(factor)

    if os.path.exists(args.output):
        if not args.force:
            p.error(f'{args.output} exists (use --force to overwrite)')
        shutil.rmtree(args.output)

    fields = {sig.key: getattr(args, sig.key) for sig in SIGNALS}
    try:
        series = read_mcap(args.mcap, fields, scale)
        n = write_bag(series, args.output, 'zstd_fast' if args.zstd else '')
    except ValueError as e:
        p.error(str(e))
    counts = ', '.join(f'{s.topic}={len(series[s.key])}' for s in SIGNALS)
    print(f'wrote {n} messages to {args.output} (mcap): {counts}')


if __name__ == '__main__':
    main()
