# https://github.com/Lasagne/Recipes/tree/master/papers/deep_residual_learning

FROM ubuntu:18.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python \
    python-pip \
    curl \
    git-core \
    && \
    rm -rf /var/lib/apt/lists/*

RUN pip install setuptools wheel
RUN pip install -r https://raw.githubusercontent.com/Lasagne/Lasagne/v0.1/requirements.txt
RUN pip install Lasagne==0.1

RUN curl -OL https://github.com/Lasagne/Recipes/archive/refs/heads/master.tar.gz && tar xvf master.tar.gz && rm master.tar.gz

