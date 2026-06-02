#!/usr/bin/env bash

set -ex

rm -rf venv
python -m venv venv
source venv/bin/activate
pip install --upgrade pip pandas numpy scikit-learn matplotlib seaborn scipy joblib
# python data-acquisition.py
# python data-processing.py
# python model-training.py
