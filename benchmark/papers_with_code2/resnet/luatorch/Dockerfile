# Following https://github.com/facebookarchive/fb.resnet.torch/blob/master/INSTALL.md

FROM ubuntu:14.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    software-properties-common \
    luarocks \
    && \
    rm -rf /var/lib/apt/lists/*

# TODO: Do the things this script does myself
RUN curl -sk https://raw.githubusercontent.com/torch/ezinstall/master/install-deps | bash -e

RUN git clone https://github.com/torch/distro.git ~/torch --recursive && \
    cd ~/torch && \
    ./install.sh

RUN luarocks install nn cunn cutorch

# RUN source /root/torch/install/bin/torch-activate && \
#     git clone -b R4 https://github.com/soumith/cudnn.torch.git ~/cudnn.torch && \
#     cd ~/cudnn.torch && \
#     luarocks make
