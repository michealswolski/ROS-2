import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from drive_bag.drive_log import Series, read_drive_csv  # noqa: E402
from drive_bag.generate_sample import generate  # noqa: E402
from drive_bag.kpi import distance_km, drive_kpis, signal_stats  # noqa: E402

PERIOD_NS = 50_000_000  # 20 Hz


def _series(indices, values=None):
    s = Series()
    for n, i in enumerate(indices):
        s.append(i * PERIOD_NS, values[n] if values else float(i))
    return s


def test_no_drops():
    st = signal_stats(_series(range(100)), 20.0)
    assert st['count'] == 100
    assert st['expected'] == 100
    assert st['dropped'] == 0
    assert st['gap_events'] == 0


def test_single_and_burst_drops():
    idx = [i for i in range(100) if i != 10 and not 50 <= i < 60]
    st = signal_stats(_series(idx), 20.0)
    assert st['dropped'] == 11
    assert st['gap_events'] == 2
    assert st['longest_gap_s'] == 0.55


def test_drops_at_edges_use_log_span():
    st = signal_stats(_series(range(5, 95)), 20.0, span_start_ns=0, span_end_ns=99 * PERIOD_NS)
    assert st['dropped'] == 10


def test_distance_constant_speed():
    # 36 km/h for 10 s = 100 m
    s = _series(range(201), [36.0] * 201)
    assert abs(distance_km(s) - 0.1) < 1e-9


def test_drive_kpis_headline():
    k = drive_kpis({
        'rpm': _series(range(10), [800, 900, 3000, 6100, 2000, 1000, 900, 800, 800, 800]),
        'speed': _series(range(10), [0, 0, 10, 20, 30, 30, 20, 10, 0, 0]),
        'pressure': _series([0, 1, 2, 3, 4, 5, 6, 9], [200] * 8),
    }, 20.0)
    assert k['max_rpm'] == 6100
    assert k['avg_speed_kph'] == 12.0
    assert k['avg_moving_speed_kph'] == 20.0
    assert k['dropped_messages'] == 2
    assert k['total_messages'] == 28


def test_sample_csv_roundtrip(tmp_path):
    path = tmp_path / 'drive.csv'
    rows = generate(str(path))
    series = read_drive_csv(str(path))
    k = drive_kpis(series, 20.0)
    assert len(series['rpm']) <= rows
    assert k['signals']['pressure']['longest_gap_s'] >= 1.6
    assert 1500 < k['max_rpm'] < 7000
    assert k['dropped_messages'] > 0
