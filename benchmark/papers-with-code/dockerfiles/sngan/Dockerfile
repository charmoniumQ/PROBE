FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && \
    apt-get install --assume-yes \
        python3 \
        python3-venv \
        git-core

RUN git clone https://github.com/pfnet-research/sngan_projection/

RUN python -m venv /venv/ && \
    /venv/bin/pip install --requirements requirements_paper.txt && \
    /venv/bin/pip uninstall cupy && \
    git clone https://github.com/cupy/cupy.git && \
    cd cupy && \
    python setup.py install
