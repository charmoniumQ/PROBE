# Following https://github.com/pytorch/examples/tree/main/imagenet

FROM pytorch:pytorch

RUN git clone https://github.com/pytorch/examples/

WORKDIR examples/imagenet

RUN pip install -r requirements.txt

# python main.py -a resnet18 --dummy
