FROM quay.io/lib/debian:12.11-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        git \
        build-essential \
        curl
# python3-dev and beyond may be needed to compile Python packages

# Make Sandia proxy work
COPY cert.pem /etc/pki/tls/cert.pem
#COPY certs/ /etc/pki/tls/certs/
ENV SSL_CERT_FILE=/etc/pki/tls/cert.pem \
    https_proxy="http://proxy.sandia.gov:80" \
    http_proxy="http://proxy.sandia.gov:80" \
    NO_PROXY="127.0.0.1,localhost,.sandia.gov"
# http_proxy ahs to be lowercase
# https://everything.curl.dev/usingcurl/proxies/env.html

# RUN curl -sSL https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "sandbox = false" --init none --no-confirm
# ENV PATH="/nix/var/nix/profiles/default/bin:$PATH" \
#     NIX_SSL_CERT_FILE="$SSL_CERT_FILE"


# Install PROBE
# RUN nix profile add --accept-flake-config 'nixpkgs#cachix' \
#     && cachix use charmonium \
#     && nix profile add github:charmoniumQ/PROBE
#RUN nix profile add --print-build-logs github:charmoniumQ/PROBE/9a82b820dad0d3310350af4c5805763193fcd292

# # De-escalate privileges
# RUN useradd --system --user-group user --create-home
# USER user
# WORKDIR /home/user

# # Install venv
RUN python3 -m venv ./venv \
    && ./venv/bin/pip config set global.index https://nexus.web.sandia.gov/repository/pypi-group/pypi \
    && ./venv/bin/pip config set global.index-url https://nexus.web.sandia.gov/repository/pypi-group/simple

# # Activate Venv
ENV PATH="/home/user/venv/bin:$PATH" \
    PS1="(venv) $PS1"
