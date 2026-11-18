#!/usr/bin/env python3

# @BEGIN main
# @PARAM data_url
# @OUT raw_data @URI file:data/raw_data.csv
# @OUT features @AS feature_names
# @OUT target @AS target_variable

import pandas as pd
import numpy as np
import os

def acquire_data():
    """
    Acquires and processes the Boston Housing dataset.
    
    @BEGIN fetch_raw_data
    @IN data_url
    @OUT raw_df @AS raw_dataset
    @END fetch_raw_data
    
    @BEGIN process_data
    @IN raw_df @AS raw_dataset
    @OUT data @AS feature_matrix
    @OUT target @AS target_variable
    @END process_data
    
    @BEGIN create_features
    @IN feature_names
    @IN data @AS feature_matrix
    @IN target @AS target_variable
    @OUT X @AS feature_dataframe
    @OUT y @AS target_series
    @END create_features
    """
    print("Acquiring Boston Housing dataset...")

    # @BEGIN fetch_raw_data
    data_url = "http://lib.stat.cmu.edu/datasets/boston"
    raw_df = pd.read_csv(data_url, sep="\s+", skiprows=22, header=None)
    # @END fetch_raw_data
    
    # @BEGIN process_data
    data = np.hstack([raw_df.values[::2, :], raw_df.values[1::2, :2]])
    target = raw_df.values[1::2, 2]
    # @END process_data

    # @BEGIN create_features
    feature_names = [
        'CRIM', 'ZN', 'INDUS', 'CHAS', 'NOX', 'RM', 'AGE', 'DIS', 'RAD',
        'TAX', 'PTRATIO', 'B', 'LSTAT'
    ]
    X = pd.DataFrame(data, columns=feature_names)
    y = pd.Series(target, name='price')
    # @END create_features

    # @BEGIN save_data
    # @IN X @AS feature_dataframe
    # @IN y @AS target_series
    # @OUT raw_data @URI file:data/raw_data.csv
    data = pd.concat([X, y], axis=1)

    os.makedirs('data', exist_ok=True)
    data.to_csv('data/raw_data.csv', index=False)
    # @END save_data

    print(f"Dataset saved with shape: {data.shape}")
    print(f"Features: {list(feature_names)}")
    print(f"Target: {y.name}")
    print("Data acquisition complete!")

    return data

# @END main

if __name__ == "__main__":
    acquire_data()