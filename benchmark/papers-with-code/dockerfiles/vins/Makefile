SHELL := /bin/bash

src/:
	git clone --depth=1 https://github.com/HKUST-Aerial-Robotics/VINS-Mono.git src/VINS-Mono

build/: src/
	source /opt/ros/$(ROS_DISTRO)/setup.bash && catkin_make

data/:
	mkdir data
	curl -o data/MH_01_easy.bag http://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/machine_hall/MH_01_easy/MH_01_easy.bag

exp0: data/ build/
	source /opt/ros/$(ROS_DISTRO)/setup.bash && roslaunch vins_estimator euroc.launch & pid=$! ; rosbag play --factor=10 data/MH_01_easy.bag ; kill $pid

exp1: data/ build/
	source /opt/ros/$(ROS_DISTRO)/setup.bash && roslaunch vins_estimator euroc_no_extrinsic_param.launch & pid=$! ; rosbag play --factor=10 data/MH_01_easy.bag ; kill $pid
