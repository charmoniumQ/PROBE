# Partially authored by ChatGPT

FROM tensorflow/tensorflow:2.19.0-gpu

WORKDIR /workspace

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git && \
    rm -rf /var/lib/apt/lists/*

# TensorFlow Model Garden
RUN git clone https://github.com/tensorflow/models.git

WORKDIR /workspace/models

RUN pip install --upgrade pip && \
    pip install -r official/requirements.txt

ENV PYTHONPATH=/workspace/models

# Directory for datasets and checkpoints
RUN mkdir -p /data /output

CMD python official/vision/train.py \
    --experiment=resnet_imagenet \
    --mode=train_and_eval \
    --model_dir=/output
