# Convenience targets; everything runs inside the ROS 2 Jazzy container.
IMAGE ?= ros2-drive-bag
RUN = docker run --rm --user "$$(id -u):$$(id -g)" -v "$(CURDIR)":/project $(IMAGE)

.PHONY: build demo test foxglove live shell

build:            ## build the Docker image (ROS 2 Jazzy + foxglove_bridge + this package)
	docker build -t $(IMAGE) .

demo: build       ## CSV -> MCAP bag -> ros2 bag play -> KPIs -> dashboard (writes results/, docs/)
	$(RUN) scripts/run_demo.sh

test: build       ## colcon test: unit, bag I/O, replay end-to-end, flake8
	docker run --rm $(IMAGE) bash -c 'cd /ws && colcon test --event-handlers console_direct+ && colcon test-result --verbose'

foxglove: build   ## verify foxglove_bridge streams the topics (automated check)
	$(RUN) scripts/foxglove_check.sh

live: build       ## replay forever with foxglove_bridge on ws://localhost:8765 (Ctrl-C to stop)
	docker run --rm -it -p 8765:8765 -v "$(CURDIR)":/project $(IMAGE) \
	    ros2 launch drive_bag replay.launch.py loop:=true foxglove:=true

shell: build      ## interactive shell with ROS 2 sourced
	docker run --rm -it -v "$(CURDIR)":/project $(IMAGE) bash
