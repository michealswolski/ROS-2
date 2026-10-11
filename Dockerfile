# ROS 2 Jazzy (Ubuntu 24.04) with rosbag2 + MCAP storage, foxglove_bridge and this package.
FROM ros:jazzy-ros-base

# Set to 0 to skip foxglove_bridge (e.g. if packages.ros.org is unreachable).
ARG WITH_FOXGLOVE_BRIDGE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-matplotlib python3-pytest python3-pip python3-protobuf \
        python3-websockets python3-zstandard python3-lz4 \
        $( [ "$WITH_FOXGLOVE_BRIDGE" = "1" ] && echo ros-jazzy-foxglove-bridge ) \
    && rm -rf /var/lib/apt/lists/*

# MCAP reader/writer for mcap_to_bag (JSON / Protobuf input logs). Not packaged in apt.
RUN pip3 install --no-cache-dir --break-system-packages --no-deps \
        mcap==1.5.0

# Writable caches so the container also works with `--user $(id -u):$(id -g)`.
ENV ROS_HOME=/tmp/ros \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /ws
COPY src/ src/
RUN . /opt/ros/jazzy/setup.sh && colcon build --symlink-install

RUN echo 'source /opt/ros/jazzy/setup.bash && source /ws/install/setup.bash' >> /etc/bash.bashrc
COPY scripts/ scripts/
WORKDIR /project
EXPOSE 8765
ENTRYPOINT ["/ws/scripts/entrypoint.sh"]
CMD ["bash"]
