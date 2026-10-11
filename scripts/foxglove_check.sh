#!/bin/bash
# Replay the bag with foxglove_bridge running and verify a Foxglove-style client
# receives /vehicle/rpm, /vehicle/speed and /vehicle/pressure over ws://localhost:8765.
#   docker run --rm -v "$PWD":/project ros2-drive-bag scripts/foxglove_check.sh
set -euo pipefail
set -m  # background jobs get their own process group so we can stop them cleanly

BAG=${BAG:-bags/sample_drive}
PORT=${PORT:-8765}

if ! ros2 pkg prefix foxglove_bridge >/dev/null 2>&1; then
    echo "foxglove_bridge is not installed (build the image with WITH_FOXGLOVE_BRIDGE=1)" >&2
    exit 1
fi

ros2 launch drive_bag replay.launch.py bag:="$BAG" rate:=5.0 loop:=true foxglove:=true \
    foxglove_port:="$PORT" output:=/tmp/replay_kpis.json > /tmp/foxglove_launch.log 2>&1 &
LAUNCH=$!
trap 'kill -INT -$LAUNCH 2>/dev/null || true; wait $LAUNCH 2>/dev/null || true' EXIT

if python3 /ws/scripts/foxglove_smoke_test.py --url "ws://localhost:$PORT" --timeout 60; then
    echo "foxglove_bridge check passed"
else
    echo "foxglove_bridge check FAILED; launch log:" >&2
    tail -50 /tmp/foxglove_launch.log >&2
    exit 1
fi
