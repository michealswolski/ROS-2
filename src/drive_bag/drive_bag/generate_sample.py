"""Generate a realistic synthetic drive log (RPM, speed, pressure) as CSV or MCAP.

Stand-in for a real logger export: a ~5 minute city -> highway -> city drive
at 20 Hz with a manual 6-speed gearbox model, plus realistic logger faults
(random single-sample drops and one 1.6 s pressure sensor dropout) so the
dropped-message KPI has something to find.

An output path ending in .mcap writes a non-ROS, JSON-encoded MCAP instead
(channels /engine {rpm, oil_pressure_kpa} and /vehicle {speed_kph}), like a
Foxglove-SDK or custom logger would; convert it with mcap_to_bag.
"""

import argparse
import csv
import json
import math
import random

from .drive_log import DEFAULT_START_EPOCH_S

# (duration_s, target_speed_kph at end of segment)
DRIVE_CYCLE = [
    (12, 0), (10, 30), (8, 50), (20, 50), (8, 0), (10, 0),        # city block + light
    (12, 60), (10, 90), (8, 105), (60, 105), (10, 115), (20, 110),  # on-ramp + highway
    (12, 70), (10, 50), (15, 50), (7, 0), (8, 0), (8, 35),          # exit + city
    (12, 35), (6, 0), (14, 0),                                       # park
]
GEAR_RATIOS = [3.82, 2.20, 1.52, 1.22, 1.02, 0.84]
FINAL_DRIVE = 3.94
TIRE_RADIUS_M = 0.316
IDLE_RPM = 780.0


def _engine_rpm(speed_kph: float, accel: float, gear: int) -> float:
    wheel_rps = (speed_kph / 3.6) / (2 * math.pi * TIRE_RADIUS_M)
    rpm = wheel_rps * 60 * FINAL_DRIVE * GEAR_RATIOS[gear]
    if speed_kph < 6:  # clutch in / slipping
        rpm = IDLE_RPM + max(accel, 0) * 900
    return max(rpm, IDLE_RPM)


def _pick_gear(speed_kph: float, gear: int, accel: float) -> int:
    up_rpm = 2900 if accel > 0.8 else 2300
    while gear < 5 and _engine_rpm(speed_kph, accel, gear) > up_rpm:
        gear += 1
    while gear > 0 and _engine_rpm(speed_kph, accel, gear) < 1250:
        gear -= 1
    return gear


def generate(path: str, rate_hz: float = 20.0, seed: int = 7) -> int:
    rng = random.Random(seed)
    dt = 1.0 / rate_hz

    targets = []
    v0 = 0.0
    for duration, v1 in DRIVE_CYCLE:
        n = int(duration * rate_hz)
        for i in range(n):
            # Smooth (cosine) transition between segment speeds.
            a = 0.5 - 0.5 * math.cos(math.pi * (i + 1) / n)
            targets.append(v0 + (v1 - v0) * a)
        v0 = v1

    n = len(targets)
    # Pressure sensor dropout: 1.6 s about 60% into the drive.
    dropout_start = int(n * 0.6)
    dropout = range(dropout_start, dropout_start + int(1.6 * rate_hz))

    rows = []
    gear = 0
    pressure = 160.0
    prev_target = 0.0
    for i, target in enumerate(targets):
        # Acceleration from the smooth profile; sensor noise goes on speed only.
        accel = (target - prev_target) / 3.6 / dt
        prev_target = target
        speed = max(0.0, target + rng.gauss(0, 0.25) * (target > 1))
        gear = _pick_gear(speed, gear, accel)
        rpm = _engine_rpm(speed, accel, gear) * (1 + 0.04 * max(accel, 0)) + rng.gauss(0, 12)
        # Oil pressure follows RPM with a lag; warms up (drops) over the drive.
        warm = 25 * math.exp(-i / (n * 0.35))
        pressure += 0.15 * ((140 + 0.075 * rpm + warm) - pressure)
        p = pressure + rng.gauss(0, 1.5)

        t = round(i * dt, 3)
        row = [f'{t:.3f}', f'{rpm:.1f}', f'{speed:.2f}', f'{p:.1f}']
        # Random single-sample logger drops per signal.
        for col, rate in ((1, 0.002), (2, 0.003), (3, 0.0015)):
            if rng.random() < rate:
                row[col] = ''
        if i in dropout:
            row[3] = ''
        rows.append(row)

    if path.endswith('.mcap'):
        _write_json_mcap(path, rows)
    else:
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['timestamp_s', 'rpm', 'speed_kph', 'pressure_kpa'])
            w.writerows(rows)
    return len(rows)


def _write_json_mcap(path: str, rows) -> None:
    from mcap.writer import Writer

    def schema(name, props):
        return json.dumps({'title': name, 'type': 'object',
                           'properties': {k: {'type': 'number'} for k in props}}).encode()

    with open(path, 'wb') as f:
        w = Writer(f)
        w.start(profile='', library='drive_bag generate_sample')
        engine = w.register_channel(
            '/engine', 'json', w.register_schema('Engine', 'jsonschema',
                                                 schema('Engine', ['rpm', 'oil_pressure_kpa'])))
        vehicle = w.register_channel(
            '/vehicle', 'json', w.register_schema('Vehicle', 'jsonschema',
                                                  schema('Vehicle', ['speed_kph'])))
        for t, rpm, speed, pressure in rows:
            t_ns = int(round(float(t) * 1e9)) + int(DEFAULT_START_EPOCH_S * 1e9)
            eng = {k: float(v) for k, v in (('rpm', rpm), ('oil_pressure_kpa', pressure)) if v}
            if eng:
                w.add_message(engine, log_time=t_ns, publish_time=t_ns,
                              data=json.dumps(eng).encode())
            if speed:
                w.add_message(vehicle, log_time=t_ns, publish_time=t_ns,
                              data=json.dumps({'speed_kph': float(speed)}).encode())
        w.finish()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('-o', '--output', default='data/sample_drive.csv',
                   help='.csv, or .mcap for a JSON-encoded (non-ROS) MCAP log')
    p.add_argument('--rate-hz', type=float, default=20.0)
    p.add_argument('--seed', type=int, default=7)
    args = p.parse_args(argv)
    n = generate(args.output, args.rate_hz, args.seed)
    print(f'wrote {n} rows to {args.output}')


if __name__ == '__main__':
    main()
