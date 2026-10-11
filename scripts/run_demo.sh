#!/bin/bash
# End-to-end demo: drive log -> rosbag2 (MCAP) -> ros2 bag play -> KPIs.
# Run inside the container from the repo root:
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/project ros2-drive-bag scripts/run_demo.sh
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

echo "== 3. Non-ROS MCAP (JSON channels, like a Foxglove-SDK logger) -> rosbag2"
TMP=$(mktemp -d)
ros2 run drive_bag generate_sample -o "$TMP/logger.mcap"
ros2 run drive_bag mcap_to_bag "$TMP/logger.mcap" -o "$TMP/from_mcap" \
    --rpm /engine:rpm --speed /vehicle:speed_kph --pressure /engine:oil_pressure_kpa
ros2 bag info "$TMP/from_mcap" | grep -E "Storage id|Messages"

echo "== 4. ros2 bag play at ${RATE}x with live KPI monitor"
ros2 launch drive_bag replay.launch.py bag:="$BAG" rate:="$RATE" output:=results/replay_kpis.json

echo "== 5. Offline KPIs from the bag"
ros2 run drive_bag bag_kpis "$BAG" -o results

echo "== 6. Bag -> CSV export and dashboard screenshot"
ros2 run drive_bag bag_to_csv "$BAG" -o "$TMP/export.csv"
head -3 "$TMP/export.csv"
ros2 run drive_bag plot_bag "$BAG" -o docs/drive_dashboard.png
rm -rf "$TMP"
