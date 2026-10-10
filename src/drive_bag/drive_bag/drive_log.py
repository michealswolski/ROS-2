"""Shared definitions for the drive log: signals, topics and CSV parsing.

This module has no ROS dependencies so it can be unit tested anywhere.
"""

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Nominal logger rate. The sample log is 20 Hz; override with --rate-hz.
DEFAULT_RATE_HZ = 20.0

# If the CSV time column holds relative seconds (not epoch), stamps are
# anchored here so the bag has a realistic wall-clock date.
DEFAULT_START_EPOCH_S = 1759327200.0  # 2025-10-01T14:00:00Z


@dataclass(frozen=True)
class Signal:
    key: str        # short name used in KPIs
    column: str     # default CSV column
    topic: str      # ROS 2 topic
    unit: str


SIGNALS: List[Signal] = [
    Signal('rpm', 'rpm', '/vehicle/rpm', 'rpm'),
    Signal('speed', 'speed_kph', '/vehicle/speed', 'km/h'),
    Signal('pressure', 'pressure_kpa', '/vehicle/pressure', 'kPa'),
]

SIGNAL_BY_TOPIC: Dict[str, Signal] = {s.topic: s for s in SIGNALS}
MSG_TYPE = 'std_msgs/msg/Float64'


@dataclass
class Series:
    """One signal as parallel lists of timestamps (ns) and values."""
    times_ns: List[int] = field(default_factory=list)
    values: List[float] = field(default_factory=list)

    def append(self, t_ns: int, value: float) -> None:
        self.times_ns.append(t_ns)
        self.values.append(value)

    def __len__(self) -> int:
        return len(self.values)


def _parse_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    text = text.strip()
    if not text or text.lower() in ('nan', 'na', 'null', 'none'):
        return None
    return float(text)


def read_drive_csv(path: str,
                   time_col: str = 'timestamp_s',
                   columns: Optional[Dict[str, str]] = None,
                   start_epoch_s: float = DEFAULT_START_EPOCH_S) -> Dict[str, Series]:
    """Read a drive log CSV into one Series per signal key.

    Blank / NaN cells mean the logger did not capture that signal on that
    row; they are skipped, so they show up as dropped messages later.
    `columns` maps signal key -> CSV column name to support other loggers.
    """
    columns = {s.key: s.column for s in SIGNALS} | (columns or {})
    series = {s.key: Series() for s in SIGNALS}

    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        missing = [c for c in [time_col, *columns.values()] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f'{path}: missing CSV column(s) {missing}; found {reader.fieldnames}')

        offset_s = None
        for row in reader:
            t = _parse_float(row[time_col])
            if t is None:
                continue
            if offset_s is None:
                # Epoch seconds are used as-is; relative times get anchored.
                offset_s = 0.0 if t > 1e9 else start_epoch_s
            # Integer ns math so 20 Hz stamps stay exact (no float rounding).
            t_ns = int(round(t * 1e9)) + int(round(offset_s * 1e9))
            for key, col in columns.items():
                value = _parse_float(row[col])
                if value is not None:
                    series[key].append(t_ns, value)
    return series
