"""Integration tests: CSV / JSON-MCAP / Protobuf-MCAP -> rosbag2 (mcap) -> read back."""
import csv
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
rosbag2_py = pytest.importorskip('rosbag2_py')

from drive_bag.bag_reader import read_bag, topic_counts  # noqa: E402, I100
from drive_bag.bag_to_csv import write_csv  # noqa: E402
from drive_bag.csv_to_bag import write_bag  # noqa: E402
from drive_bag.drive_log import DEFAULT_START_EPOCH_S, read_drive_csv  # noqa: E402
from drive_bag.generate_sample import generate  # noqa: E402

START_NS = int(DEFAULT_START_EPOCH_S * 1e9)


def _write_csv(path, rows):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['timestamp_s', 'rpm', 'speed_kph', 'pressure_kpa'])
        w.writerows(rows)


def test_csv_bag_roundtrip(tmp_path):
    src = tmp_path / 'in.csv'
    _write_csv(src, [['0.0', '800', '0', '200'],
                     ['0.05', '900.5', '', '201'],
                     ['0.1', '1000', '1.5', '']])
    bag = tmp_path / 'bag'
    assert write_bag(read_drive_csv(str(src)), str(bag)) == 7

    meta = rosbag2_py.Info().read_metadata(str(bag), '')
    assert meta.storage_identifier == 'mcap'
    assert topic_counts(str(bag)) == {'/vehicle/rpm': 3, '/vehicle/speed': 2,
                                      '/vehicle/pressure': 2}
    series = read_bag(str(bag))
    assert series['rpm'].values == [800.0, 900.5, 1000.0]
    assert series['speed'].times_ns == [START_NS, START_NS + 100_000_000]

    out = tmp_path / 'out.csv'
    assert write_csv(series, str(out)) == 3
    back = read_drive_csv(str(out))
    for key in ('rpm', 'speed', 'pressure'):
        assert back[key].values == series[key].values
        assert back[key].times_ns == series[key].times_ns


def test_sample_csv_to_bag_matches_csv_kpis(tmp_path):
    from drive_bag.kpi import drive_kpis
    src = tmp_path / 'drive.csv'
    generate(str(src))
    csv_series = read_drive_csv(str(src))
    write_bag(csv_series, str(tmp_path / 'bag'))
    assert drive_kpis(read_bag(str(tmp_path / 'bag')), 20.0) == drive_kpis(csv_series, 20.0)


def test_empty_input_rejected(tmp_path):
    src = tmp_path / 'empty.csv'
    _write_csv(src, [])
    with pytest.raises(ValueError, match='no samples'):
        write_bag(read_drive_csv(str(src)), str(tmp_path / 'bag'))


def test_missing_csv_column(tmp_path):
    src = tmp_path / 'bad.csv'
    src.write_text('time,rpm\n0,800\n')
    with pytest.raises(ValueError, match='missing CSV column'):
        read_drive_csv(str(src))


def test_json_mcap_to_bag(tmp_path):
    pytest.importorskip('mcap')
    from drive_bag.mcap_to_bag import DEFAULT_FIELDS, read_mcap
    src = tmp_path / 'drive.mcap'
    generate(str(src))
    csv_path = tmp_path / 'drive.csv'
    generate(str(csv_path))

    series = read_mcap(str(src), DEFAULT_FIELDS)
    expected = read_drive_csv(str(csv_path))
    for key in ('rpm', 'speed', 'pressure'):
        assert series[key].values == expected[key].values
        assert series[key].times_ns == expected[key].times_ns

    write_bag(series, str(tmp_path / 'bag'))
    assert sum(topic_counts(str(tmp_path / 'bag')).values()) == sum(
        len(s) for s in expected.values())


def test_json_mcap_nested_fields_and_scale(tmp_path):
    mcap_writer = pytest.importorskip('mcap.writer')
    from drive_bag.mcap_to_bag import read_mcap
    src = tmp_path / 'nested.mcap'
    with open(src, 'wb') as f:
        w = mcap_writer.Writer(f)
        w.start()
        ch = w.register_channel('/can', 'json', w.register_schema('Can', 'jsonschema', b'{}'))
        for i, msg in enumerate([{'engine': {'rpm': 800}, 'wheels': [{'v': 10.0}], 'p': 1},
                                 {'engine': {}, 'wheels': [{'v': 12.0}], 'p': 2}]):
            w.add_message(ch, log_time=i * 50_000_000, publish_time=0,
                          data=json.dumps(msg).encode())
        w.finish()
    s = read_mcap(str(src), {'rpm': '/can:engine.rpm', 'speed': '/can:wheels.0.v',
                             'pressure': '/can:p'}, scale={'speed': 3.6})
    assert s['rpm'].values == [800.0]           # missing field = dropped sample
    assert s['speed'].values == [36.0, 43.2]
    assert s['pressure'].times_ns == [0, 50_000_000]


def test_protobuf_mcap_to_bag(tmp_path):
    mcap_writer = pytest.importorskip('mcap.writer')
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
    from drive_bag.mcap_to_bag import read_mcap

    fdp = descriptor_pb2.FileDescriptorProto(name='drive.proto', package='drive', syntax='proto3')
    for name, fields in (('Engine', ['rpm', 'oil_pressure_kpa']), ('Vehicle', ['speed_kph'])):
        m = fdp.message_type.add(name=name)
        for i, field in enumerate(fields, 1):
            m.field.add(name=field, number=i,
                        type=descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
                        label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL)
    pool = descriptor_pool.DescriptorPool()
    pool.Add(fdp)

    def cls(name):
        desc = pool.FindMessageTypeByName(name)
        if hasattr(message_factory, 'GetMessageClass'):
            return message_factory.GetMessageClass(desc)
        return message_factory.MessageFactory(pool).GetPrototype(desc)

    Engine, Vehicle = cls('drive.Engine'), cls('drive.Vehicle')
    fds = descriptor_pb2.FileDescriptorSet(file=[fdp]).SerializeToString()
    src = tmp_path / 'drive_pb.mcap'
    with open(src, 'wb') as f:
        w = mcap_writer.Writer(f)
        w.start()
        engine = w.register_channel(
            '/engine', 'protobuf', w.register_schema('drive.Engine', 'protobuf', fds))
        vehicle = w.register_channel(
            '/vehicle', 'protobuf', w.register_schema('drive.Vehicle', 'protobuf', fds))
        for i in range(10):
            t = i * 50_000_000
            w.add_message(engine, log_time=t, publish_time=t,
                          data=Engine(rpm=800 + i, oil_pressure_kpa=200).SerializeToString())
            w.add_message(vehicle, log_time=t, publish_time=t,
                          data=Vehicle(speed_kph=i * 1.5).SerializeToString())
        w.finish()

    series = read_mcap(str(src), {'rpm': '/engine:rpm', 'speed': '/vehicle:speed_kph',
                                  'pressure': '/engine:oil_pressure_kpa'})
    assert series['rpm'].values == [800.0 + i for i in range(10)]
    assert series['speed'].values[-1] == 13.5
    write_bag(series, str(tmp_path / 'bag'))
    assert topic_counts(str(tmp_path / 'bag'))['/vehicle/pressure'] == 10


def test_ros2_mcap_input_gives_hint(tmp_path):
    pytest.importorskip('mcap')
    from drive_bag.mcap_to_bag import read_mcap
    src = tmp_path / 'csv.csv'
    _write_csv(src, [['0', '800', '1', '200']])
    write_bag(read_drive_csv(str(src)), str(tmp_path / 'bag'))
    with pytest.raises(ValueError, match='already ROS 2'):
        read_mcap(str(tmp_path / 'bag' / 'bag_0.mcap'), {'rpm': '/vehicle/rpm:data'})
