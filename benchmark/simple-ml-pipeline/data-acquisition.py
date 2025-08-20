#!/usr/bin/env python3

import pandas as pd
import numpy as np
import os

def acquire_data():

    print("Acquiring Boston Housing dataset...")

    data_url = "http://lib.stat.cmu.edu/datasets/boston"
    raw_df = pd.read_csv(data_url, sep="\s+", skiprows=22, header=None)
    data = np.hstack([raw_df.values[::2, :], raw_df.values[1::2, :2]])
    target = raw_df.values[1::2, 2]

    feature_names = [
        'CRIM', 'ZN', 'INDUS', 'CHAS', 'NOX', 'RM', 'AGE', 'DIS', 'RAD',
        'TAX', 'PTRATIO', 'B', 'LSTAT'
    ]
    X = pd.DataFrame(data, columns=feature_names)
    y = pd.Series(target, name='price')

    data = pd.concat([X, y], axis=1)

    os.makedirs('data', exist_ok=True)

    data.to_csv('data/raw_data.csv', index=False)

    print(f"Dataset saved with shape: {data.shape}")
    print(f"Features: {list(feature_names)}")
    print(f"Target: {y.name}")
    print("Data acquisition complete!")

    return data

if __name__ == "__main__":
    acquire_data()