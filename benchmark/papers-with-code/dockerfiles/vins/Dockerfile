FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && \
    apt-get install --assume-yes \
        git-core \
        software-properties-common \
        libceres-dev \
        gnupg2 \
        lsb-release \
        curl \
        g++

ENV ROS_DISTRO=noetic

RUN curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc \
        | apt-key add - && \
    sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main"' \
        > /etc/apt/sources.list.d/ros-latest.list && \
    apt-get update && \
    apt-get install --assume-yes \
        ros-$ROS_DISTRO-cv-bridge \
        ros-$ROS_DISTRO-nav-msgs \
        ros-$ROS_DISTRO-visualization-msgs \
        ros-$ROS_DISTRO-tf \
        ros-$ROS_DISTRO-message-filters \
        ros-$ROS_DISTRO-image-transport \
    && sudo rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY Makefile /work
