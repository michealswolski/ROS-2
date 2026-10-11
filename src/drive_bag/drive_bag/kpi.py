"""Drive KPI math. Pure Python, no ROS dependencies."""

from typing import Dict, Optional

from .drive_log import Series

# A gap counts as dropped samples once it exceeds this many nominal periods.
GAP_TOLERANCE_PERIODS = 1.5
# Engine idling: vehicle stopped with the engine running.
IDLE_SPEED_KPH = 1.0
# Hard braking / acceleration threshold and the window used to measure it
# (a window rather than sample-to-sample differences so sensor noise is ignored).
HARSH_ACCEL_MPS2 = 3.0
ACCEL_WINDOW_S = 1.0


def signal_stats(series: Series, rate_hz: float,
                 span_start_ns: Optional[int] = None,
                 span_end_ns: Optional[int] = None) -> dict:
    """Count, min/max/mean and dropped-sample stats for one signal.

    Dropped samples are found from timestamp gaps against the nominal rate.
    The span defaults to the signal's own first/last sample; pass the whole
    log's span to also count samples missing at the start or end.
    """
    n = len(series)
    if n == 0:
        return {'count': 0, 'expected': 0, 'dropped': 0}

    t = series.times_ns
    v = series.values
    period_ns = 1e9 / rate_hz
    start = t[0] if span_start_ns is None else min(span_start_ns, t[0])
    end = t[-1] if span_end_ns is None else max(span_end_ns, t[-1])

    expected = int(round((end - start) / period_ns)) + 1
    gaps = 0
    longest_gap_ns = 0
    for a, b in zip(t, t[1:]):
        dt = b - a
        longest_gap_ns = max(longest_gap_ns, dt)
        if dt > GAP_TOLERANCE_PERIODS * period_ns:
            gaps += 1

    return {
        'count': n,
        'expected': expected,
        'dropped': max(expected - n, 0),
        'drop_rate_pct': round(100.0 * max(expected - n, 0) / expected, 3),
        'gap_events': gaps,
        'longest_gap_s': round(longest_gap_ns / 1e9, 3),
        'min': round(min(v), 3),
        'max': round(max(v), 3),
        'mean': round(sum(v) / n, 3),
    }


def distance_km(speed: Series) -> float:
    """Trapezoidal integration of speed (km/h) over time."""
    total = 0.0
    t, v = speed.times_ns, speed.values
    for i in range(1, len(v)):
        dt_h = (t[i] - t[i - 1]) / 3.6e12
        total += 0.5 * (v[i] + v[i - 1]) * dt_h
    return total


def idle_time_s(speed: Series) -> float:
    """Time spent at standstill (speed below IDLE_SPEED_KPH)."""
    total = 0
    t, v = speed.times_ns, speed.values
    for i in range(1, len(v)):
        if v[i] < IDLE_SPEED_KPH and v[i - 1] < IDLE_SPEED_KPH:
            total += t[i] - t[i - 1]
    return total / 1e9


def harsh_events(speed: Series, threshold_mps2: float = HARSH_ACCEL_MPS2,
                 window_s: float = ACCEL_WINDOW_S) -> Dict[str, int]:
    """Count hard-acceleration and hard-braking events.

    Acceleration is the speed change over `window_s`. An event starts when
    |accel| crosses the threshold and ends once it falls below 80% of it, so
    a value hovering at the threshold is counted once.
    """
    t, v = speed.times_ns, speed.values
    window_ns = window_s * 1e9
    counts = {'hard_accel': 0, 'hard_brake': 0}
    state = None  # current event: 'hard_accel', 'hard_brake' or None
    j = 0
    for i in range(len(v)):
        while t[i] - t[j] > window_ns:
            j += 1
        dt = (t[i] - t[j]) / 1e9
        accel = (v[i] - v[j]) / 3.6 / dt if dt >= 0.5 * window_s else 0.0
        if state is None:
            if accel > threshold_mps2:
                state = 'hard_accel'
            elif accel < -threshold_mps2:
                state = 'hard_brake'
            if state:
                counts[state] += 1
        elif abs(accel) < 0.8 * threshold_mps2 or (accel > 0) != (state == 'hard_accel'):
            state = None
    return counts


def drive_kpis(series: Dict[str, Series], rate_hz: float) -> dict:
    """Headline KPIs plus per-signal stats for a whole drive."""
    non_empty = [s for s in series.values() if len(s)]
    if not non_empty:
        raise ValueError('no samples in drive log')
    span_start = min(s.times_ns[0] for s in non_empty)
    span_end = max(s.times_ns[-1] for s in non_empty)

    per_signal = {k: signal_stats(s, rate_hz, span_start, span_end) for k, s in series.items()}

    speed = series.get('speed', Series())
    moving = [x for x in speed.values if x > IDLE_SPEED_KPH]
    harsh = harsh_events(speed) if len(speed) else {}

    return {
        'duration_s': round((span_end - span_start) / 1e9, 2),
        'nominal_rate_hz': rate_hz,
        'max_rpm': per_signal.get('rpm', {}).get('max'),
        'avg_speed_kph': per_signal.get('speed', {}).get('mean'),
        'avg_moving_speed_kph': round(sum(moving) / len(moving), 2) if moving else None,
        'max_speed_kph': per_signal.get('speed', {}).get('max'),
        'distance_km': round(distance_km(speed), 3),
        'idle_time_s': round(idle_time_s(speed), 2),
        'hard_brake_events': harsh.get('hard_brake'),
        'hard_accel_events': harsh.get('hard_accel'),
        'min_pressure_kpa': per_signal.get('pressure', {}).get('min'),
        'max_pressure_kpa': per_signal.get('pressure', {}).get('max'),
        'dropped_messages': sum(s['dropped'] for s in per_signal.values()),
        'total_messages': sum(s['count'] for s in per_signal.values()),
        'signals': per_signal,
    }


def kpis_markdown(k: dict) -> str:
    lines = [
        '| KPI | Value |',
        '|---|---|',
        f"| Duration | {k['duration_s']} s |",
        f"| Max RPM | {k['max_rpm']:.0f} rpm |",
        f"| Average speed (all samples) | {k['avg_speed_kph']:.1f} km/h |",
        f"| Average speed (moving, >1 km/h) | {k['avg_moving_speed_kph']:.1f} km/h |",
        f"| Max speed | {k['max_speed_kph']:.1f} km/h |",
        f"| Distance | {k['distance_km']:.2f} km |",
        f"| Idle time (stopped) | {k['idle_time_s']:.1f} s |",
        f'| Hard braking / hard acceleration events (> {HARSH_ACCEL_MPS2:g} m/s²) | '
        f"{k['hard_brake_events']} / {k['hard_accel_events']} |",
        f"| Pressure min / max | {k['min_pressure_kpa']:.0f} / {k['max_pressure_kpa']:.0f} kPa |",
        f"| Messages recorded | {k['total_messages']} |",
        f"| Dropped messages | {k['dropped_messages']} |",
        '',
        '| Signal | Count | Expected | Dropped | Drop rate | Gap events | Longest gap |',
        '|---|---|---|---|---|---|---|',
    ]
    for name, s in k['signals'].items():
        lines.append(
            f"| {name} | {s['count']} | {s['expected']} | {s['dropped']} | "
            f"{s['drop_rate_pct']}% | {s['gap_events']} | {s['longest_gap_s']} s |")
    return '\n'.join(lines) + '\n'
