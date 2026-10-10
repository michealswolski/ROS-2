#!/bin/bash
# End-to-end demo: CSV drive log -> rosbag2 (MCAP) -> ros2 bag play -> KPIs.
# Run inside the container from the repo root:
#   docker run --rm -v "$PWD":/project ros2-drive-bag scripts/run_demo.sh
set -euo pipefail

CSV=${CSV:-data/sample_drive.csv}
BAG=${BAG:-bags/sample_drive}
RATE=${RATE:-5.0}

mkdir -p results docs

echo "== 1. ROS 2 distro: ${ROS_DISTRO}"
ros2 bag list storage

echo "== 2. CSV -> rosbag2 (storage: mcap)"
[ -f "$CSV" ] || ros2 run drive_bag generate_sample -o "$CSV"
ros2 run drive_bag csv_to_bag "$CSV" -o "$BAG" --force
ros2 bag info "$BAG" | tee results/bag_info.txt

echo "== 3. ros2 bag play at ${RATE}x with live KPI monitor"
ros2 launch drive_bag replay.launch.py bag:="$BAG" rate:="$RATE" output:=results/replay_kpis.json

echo "== 4. Offline KPIs from the bag"
ros2 run drive_bag bag_kpis "$BAG" -o results

echo "== 5. Dashboard screenshot"
ros2 run drive_bag plot_bag "$BAG" -o docs/drive_dashboard.png
