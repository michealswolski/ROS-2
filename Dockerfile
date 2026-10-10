# ROS 2 Jazzy (Ubuntu 24.04) with rosbag2 + MCAP storage plugin, plus this package.
FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-matplotlib python3-pytest \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
COPY src/ src/
RUN . /opt/ros/jazzy/setup.sh && colcon build --symlink-install

# Source ROS + the workspace in every shell.
RUN echo 'source /opt/ros/jazzy/setup.bash && source /ws/install/setup.bash' >> /root/.bashrc
COPY scripts/ scripts/
WORKDIR /project
ENTRYPOINT ["/ws/scripts/entrypoint.sh"]
CMD ["bash"]
