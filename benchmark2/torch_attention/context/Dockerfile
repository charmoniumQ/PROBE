FROM docker.io/library/ubuntu:26.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-full && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /venv
RUN /venv/bin/pip install torch>=2.0 numpy matplotlib requests
