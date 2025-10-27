FROM ubuntu:14.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && \
    apt-get install --assume-yes \
        git-core \
        libprotobuf-dev \
        libleveldb-dev \
        libsnappy-dev \
        libopencv-dev \
        libhdf5-serial-dev \
        protobuf-compiler \
        libboost-all-dev \
        freeglut3-dev \
        build-essential \
        libx11-dev \
        libxmu-dev \
        libxi-dev \
        libgl1-mesa-glx \
        libglu1-mesa \
        libglu1-mesa-dev \
        libatlas-base-dev \
        libgflags-dev \
        libcublas5.5 \
        wget

# RUN wget \
#         https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1404/x86_64/cuda-license-10-1_10.1.243-1_amd64.deb \
#         https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1404/x86_64/libcublas10_10.2.1.243-1_amd64.deb \
#         https://developer.download.nvidia.com/compute/cuda/repos/ubuntu1404/x86_64/libcublas-dev_10.2.1.243-1_amd64.deb \
#     && \
#     dpkg --install ./cuda-license-10-1_10.1.243-1_amd64.deb ./libcublas10_10.2.1.243-1_amd64.deb ./libcublas-dev_10.2.1.243-1_amd64.deb

RUN apt-get install --assume-yes nvidia-cuda-dev

RUN git clone --recursive https://github.com/torrvision/crfasrnn.git && \
    git -C crfasrnn checkout 215666972c5e4c9fb10f965d2aab056b6f3f91fe && \
    git -C crfasrnn submodule update --recursive && \
    # make --directory=crfasrnn/caffe
    true
