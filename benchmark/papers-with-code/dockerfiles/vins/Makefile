src/VINS-Mono:
	git clone --depth=1 https://github.com/HKUST-Aerial-Robotics/VINS-Mono.git src/VINS-Mono

something:
	source /opt/ros/kinetic/setup.bash
	catkin_make

data/MH_01_easy.bag:
	curl -o MH_01_easy.bag http://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/machine_hall/MH_01_easy/MH_01_easy.bag

exp0:
	source ~/catkin_ws/devel/setup.bash
	roslaunch vins_estimator euroc.launch &
	pid=$!
	rosbag play --factor=10 MH_01_easy.bag
	killkill $pid $pid

exp1:
	source ~/catkin_ws/devel/setup.bash
	roslaunch vins_estimator euroc_no_extrinsic_param.launch &
	pid=$!
	rosbag play --factor=10 MH_01_easy.bag
	killkill $pid $pid
