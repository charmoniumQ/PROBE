#!/usr/bin/env python3

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib
import os

def preprocess_data():

    if not os.path.exists('data/raw_data.csv'):
        raise FileNotFoundError("Raw data not found. Run data acquisition first.")

    data = pd.read_csv('data/raw_data.csv')
    print(f"Loaded data with shape: {data.shape}")

    print("\nData Info:")
    print(data.info())
    print("\nMissing values:")
    print(data.isnull().sum())

    if data.isnull().sum().sum() > 0:
        print("Handling missing values...")
        data = data.fillna(data.median())

    X = data.drop('price', axis=1)
    y = data['price']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, shuffle=True
    )
    print(f"Train set size: {X_train.shape[0]}")
    print(f"Test set size: {X_test.shape[0]}")

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    X_train_scaled = pd.DataFrame(
        X_train_scaled,
        columns=X_train.columns,
        index=X_train.index
    )
    X_test_scaled = pd.DataFrame(
        X_test_scaled,
        columns=X_test.columns,
        index=X_test.index
    )

    os.makedirs('data/processed', exist_ok=True)

    X_train_scaled.to_csv('data/processed/X_train.csv', index=False)
    X_test_scaled.to_csv('data/processed/X_test.csv', index=False)
    y_train.to_csv('data/processed/y_train.csv', index=False)
    y_test.to_csv('data/processed/y_test.csv', index=False)

    os.makedirs('models', exist_ok=True)
    joblib.dump(scaler, 'models/scaler.pkl')

    print("\nPreprocessing Statistics:")
    print(f"Feature means: {X_train_scaled.mean().round(3).to_dict()}")
    print(f"Feature stds: {X_train_scaled.std().round(3).to_dict()}")
    print(f"Target range: {y_train.min():.2f} - {y_train.max():.2f}")

    print("Data preprocessing complete!")

    return X_train_scaled, X_test_scaled, y_train, y_test

if __name__ == "__main__":
    preprocess_data()