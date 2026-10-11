"""Export the /vehicle/* topics of a rosbag2 bag to a CSV (one row per timestamp)."""

import argparse

from .bag_reader import read_bag
from .drive_log import SIGNALS


def write_csv(series, path: str, relative: bool = True) -> int:
    rows = {}
    for sig in SIGNALS:
        for t, v in zip(series[sig.key].times_ns, series[sig.key].values):
            rows.setdefault(t, {})[sig.key] = v
    t0 = min(rows) if rows and relative else 0
    with open(path, 'w') as f:
        f.write(','.join(['timestamp_s'] + [s.column for s in SIGNALS]) + '\n')
        for t in sorted(rows):
            # repr() keeps full float precision so CSV -> bag -> CSV round-trips.
            cells = [f'{(t - t0) / 1e9:.9f}'.rstrip('0').rstrip('.')]
            cells += [repr(rows[t][s.key]) if s.key in rows[t] else '' for s in SIGNALS]
            f.write(','.join(cells) + '\n')
    return len(rows)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag', help='rosbag2 directory')
    p.add_argument('-o', '--output', required=True, help='CSV file to write')
    p.add_argument('--epoch', action='store_true',
                   help='write Unix epoch seconds instead of time since start')
    args = p.parse_args(argv)
    n = write_csv(read_bag(args.bag), args.output, relative=not args.epoch)
    print(f'wrote {n} rows to {args.output}')


if __name__ == '__main__':
    main()
