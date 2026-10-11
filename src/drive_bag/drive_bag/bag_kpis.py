"""Compute drive KPIs (max RPM, average speed, dropped messages...) from a bag."""

import argparse
import json
import os

from .bag_reader import read_bag
from .drive_log import DEFAULT_RATE_HZ
from .kpi import drive_kpis, kpis_markdown


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag', help='rosbag2 directory (mcap or sqlite3)')
    p.add_argument('--rate-hz', type=float, default=DEFAULT_RATE_HZ,
                   help='nominal logger rate used to detect dropped samples')
    p.add_argument('-o', '--output-dir', default='results',
                   help='directory for kpis.json and kpis.md')
    args = p.parse_args(argv)

    kpis = drive_kpis(read_bag(args.bag), args.rate_hz)
    kpis['bag'] = os.path.normpath(args.bag)

    os.makedirs(args.output_dir, exist_ok=True)
    with open(os.path.join(args.output_dir, 'kpis.json'), 'w') as f:
        json.dump(kpis, f, indent=2)
        f.write('\n')
    md = kpis_markdown(kpis)
    with open(os.path.join(args.output_dir, 'kpis.md'), 'w') as f:
        f.write(md)
    print(md)
    print(f'wrote {args.output_dir}/kpis.json and {args.output_dir}/kpis.md')


if __name__ == '__main__':
    main()
