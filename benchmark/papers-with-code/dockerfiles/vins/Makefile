SHELL := /bin/bash

src/:
	git clone --depth=1 https://github.com/HKUST-Aerial-Robotics/VINS-Mono.git src/VINS-Mono

build/: src/
	source /opt/ros/$(ROS_DISTRO)/setup.bash && catkin_make

data/:
	mkdir data
	cp /host/MH_01_easy.bag data
	#curl -o data/MH_01_easy.bag http://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/machine_hall/MH_01_easy/MH_01_easy.bag

# Can extend the experiment by
# 1. Lower the --start
# 2. Reduce the --rate
# 3. Play more bags from EUROC
# 4. Repeat with euroc_no_extrinsic_param
exp: data/ build/
	source devel/setup.bash ; roslaunch vins_estimator euroc.launch & pid=$$! ; sleep 5 ; rosbag play --start=100 --rate=10 data/MH_01_easy.bag ; kill $$pid ; wait $$pid
