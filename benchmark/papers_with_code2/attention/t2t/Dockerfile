FROM ubuntu:18.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    python3-pip \
    build-essential \
    cmake \
    && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip setuptools

# tensor2tensor hard requires tensorflow-probabiliyt at 0.17.0
# Tensorflow-probability has unmarked dependency on tensorflow
# https://github.com/tensorflow/probability/issues/1752
# Therefore, we pick a tensorflow very soon before the release of tensorflow-probability 0.17.0, which was June 20, 2019.
# Tensorflow 1.14.0 was released June 19, 2019
RUN pip3 install tensor2tensor tensorflow-probability==0.17.0 tensorflow==1.14.0 keras opencv-python==3.4.0.14
