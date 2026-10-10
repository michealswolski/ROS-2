"""Render a drive dashboard PNG (RPM / speed / pressure + KPIs) straight from a bag."""

import argparse
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

from .bag_reader import read_bag  # noqa: E402
from .drive_log import DEFAULT_RATE_HZ, SIGNALS  # noqa: E402
from .kpi import GAP_TOLERANCE_PERIODS, drive_kpis  # noqa: E402

SURFACE = '#fcfcfb'
TEXT = '#0b0b0b'
TEXT_2 = '#52514e'
GRID = '#e4e3df'
GAP_FILL = '#d6d4cf'
SERIES = ['#2a78d6', '#eb6834', '#1baf7a']  # categorical slots 1-3


def _gaps(times_s, period_s):
    return [(a, b) for a, b in zip(times_s, times_s[1:]) if b - a > GAP_TOLERANCE_PERIODS * period_s]


def render(bag_dir: str, out_png: str, rate_hz: float) -> dict:
    series = read_bag(bag_dir)
    k = drive_kpis(series, rate_hz)
    t0 = min(s.times_ns[0] for s in series.values() if len(s))

    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 10, 'text.color': TEXT,
        'axes.labelcolor': TEXT_2, 'xtick.color': TEXT_2, 'ytick.color': TEXT_2,
        'axes.edgecolor': GRID, 'axes.facecolor': SURFACE, 'figure.facecolor': SURFACE,
    })
    fig = plt.figure(figsize=(12, 8.2))
    grid = fig.add_gridspec(4, 1, height_ratios=[0.55, 1, 1, 1], hspace=0.35)

    # KPI strip.
    ax_k = fig.add_subplot(grid[0])
    ax_k.axis('off')
    tiles = [
        ('Max RPM', f"{k['max_rpm']:.0f}"),
        ('Avg speed', f"{k['avg_speed_kph']:.1f} km/h"),
        ('Max speed', f"{k['max_speed_kph']:.0f} km/h"),
        ('Distance', f"{k['distance_km']:.2f} km"),
        ('Dropped msgs', f"{k['dropped_messages']} / {k['dropped_messages'] + k['total_messages']}"),
    ]
    for i, (label, value) in enumerate(tiles):
        x = 0.01 + i * 0.2
        ax_k.text(x, 0.78, label, fontsize=10, color=TEXT_2, transform=ax_k.transAxes)
        ax_k.text(x, 0.2, value, fontsize=19, weight='bold', color=TEXT, transform=ax_k.transAxes)
    fig.suptitle(f'Drive replay from rosbag2 (MCAP): {os.path.basename(os.path.normpath(bag_dir))}',
                 x=0.125, ha='left', fontsize=14, weight='bold', y=0.97)

    period_s = 1.0 / rate_hz
    axes = []
    for i, sig in enumerate(SIGNALS):
        ax = fig.add_subplot(grid[i + 1], sharex=axes[0] if axes else None)
        axes.append(ax)
        s = series[sig.key]
        ts = [(t - t0) / 1e9 for t in s.times_ns]
        for a, b in _gaps(ts, period_s):
            # Widen tiny gaps so single dropped samples stay visible.
            mid, half = (a + b) / 2, max((b - a) / 2, 0.6)
            ax.axvspan(mid - half, mid + half, color=GAP_FILL, lw=0, zorder=0)
        ax.plot(ts, s.values, color=SERIES[i], lw=1.4, zorder=2)
        ax.set_ylabel(sig.unit)
        st = k['signals'][sig.key]
        ax.set_title(f'{sig.topic}   max {st["max"]:.0f}  mean {st["mean"]:.1f}  '
                     f'dropped {st["dropped"]}', loc='left', fontsize=10.5, color=TEXT)
        ax.grid(axis='y', color=GRID, lw=0.8)
        ax.spines[['top', 'right']].set_visible(False)
        ax.margins(x=0)
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('time since start of drive [s]   (grey bands = logger gaps / dropped samples)')

    os.makedirs(os.path.dirname(out_png) or '.', exist_ok=True)
    fig.savefig(out_png, dpi=110, bbox_inches='tight')
    plt.close(fig)
    return k


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag')
    p.add_argument('-o', '--output', default='docs/drive_dashboard.png')
    p.add_argument('--rate-hz', type=float, default=DEFAULT_RATE_HZ)
    args = p.parse_args(argv)
    render(args.bag, args.output, args.rate_hz)
    print(f'wrote {args.output}')


if __name__ == '__main__':
    main()
