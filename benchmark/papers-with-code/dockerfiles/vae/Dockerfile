FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install --assume-yes \
        build-essential \
        cmake \
        curl \
        git-core \
        libatlas-base-dev \
        libboost-all-dev \
        libgflags-dev \
        libgoogle-glog-dev \
        libhdf5-serial-dev \
        libleveldb-dev \
        liblmdb-dev \
        libopencv-dev \
        libprotobuf-dev \
        libsnappy-dev \
        protobuf-compiler \
        python \
        python-dev \
        python-pip \
        wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY Makefile /work
