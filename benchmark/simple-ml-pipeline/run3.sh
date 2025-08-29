#!/usr/bin/env bash

set -ex

source venv/bin/activate
python data-acquisition.py
python data-processing.py
python model-training.py
