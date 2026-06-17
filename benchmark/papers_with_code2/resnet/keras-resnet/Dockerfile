FROM ubuntu:18.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    sed \
    && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip setuptools
RUN pip3 install tensorflow==1.10.0 keras==2.2.0 "numpy<1.24.0"

RUN curl --fail --show-error --silent --remote-name --location https://github.com/raghakot/keras-resnet/archive/refs/heads/master.tar.gz && \
    tar --extract --file master.tar.gz && \
    rm master.tar.gz

WORKDIR keras-resnet-master

RUN sed --in-place 's/nb_epoch = 200/nb_epoch = 1/' cifar10.py && \
    sed --in-place '33a \
X_train = X_train[:len(X_train) // 100]; \
Y_train = Y_train[:len(Y_train) // 100]; \
X_test = X_test[:len(X_test) // 100]; \
Y_test = Y_test[:len(Y_test) // 100]' cifar10.py

