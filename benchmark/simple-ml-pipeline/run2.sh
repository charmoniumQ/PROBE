#!/usr/bin/env bash

set -ex

rm -rf venv
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install pandas
pip install numpy
pip install scikit-learn
pip install matplotlib
pip install seaborn
pip install scipy
pip install joblib
# python data-acquisition.py
# python data-processing.py
# python model-training.py
