#!/usr/bin/env python3

# model training and results comparison script

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import cross_val_score, GridSearchCV
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import os
import json

def load_training_data():
    try:
        X_train = pd.read_csv('data/processed/X_train.csv')
        y_train = pd.read_csv('data/processed/y_train.csv').squeeze()
        return X_train, y_train
    except FileNotFoundError:
        raise FileNotFoundError("Preprocessed data not found. Run preprocessing first.")

def train_models(X_train, y_train):
    print("Training multiple models...")

    models = {
        'linear_regression': LinearRegression(),
        'ridge_regression': Ridge(alpha=1.0),
        'random_forest': RandomForestRegressor(n_estimators=100, random_state=42)
    }

    model_results = {}
    trained_models = {}

    for name, model in models.items():
        print(f"\nTraining {name}...")

        cv_scores = cross_val_score(
            model, X_train, y_train,
            cv=5, scoring='neg_mean_squared_error'
        )

        model.fit(X_train, y_train)

        model_results[name] = {
            'cv_mse': -cv_scores.mean(),
            'cv_std': cv_scores.std(),
            'cv_r2': cross_val_score(model, X_train, y_train, cv=5, scoring='r2').mean()
        }

        trained_models[name] = model

        print(f"CV MSE: {model_results[name]['cv_mse']:.3f} (+/- {model_results[name]['cv_std']:.3f})")
        print(f"CV R²: {model_results[name]['cv_r2']:.3f}")

    return model_results, trained_models

def hyperparameter_tuning(X_train, y_train):
    print("\nPerforming hyperparameter tuning for Random Forest...")

    param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [None, 10, 20],
        'min_samples_split': [2, 5, 10]
    }

    rf = RandomForestRegressor(random_state=42)
    grid_search = GridSearchCV(
        rf, param_grid, cv=3,
        scoring='neg_mean_squared_error',
        n_jobs=1, verbose=1
    )

    grid_search.fit(X_train, y_train)

    print(f"Best parameters: {grid_search.best_params_}")
    print(f"Best CV score: {-grid_search.best_score_:.3f}")

    return grid_search.best_estimator_

def train_pipeline():
    print("Starting model training pipeline...")

    X_train, y_train = load_training_data()
    print(f"Training data loaded: {X_train.shape}")

    model_results, trained_models = train_models(X_train, y_train)

    best_model_name = min(model_results.keys(),
                         key=lambda x: model_results[x]['cv_mse'])
    print(f"\nBest baseline model: {best_model_name}")

    tuned_model = hyperparameter_tuning(X_train, y_train)

    tuned_cv_scores = cross_val_score(
        tuned_model, X_train, y_train,
        cv=5, scoring='neg_mean_squared_error'
    )
    tuned_mse = -tuned_cv_scores.mean()

    print(f"\nTuned Random Forest CV MSE: {tuned_mse:.3f}")

    if tuned_mse < model_results[best_model_name]['cv_mse']:
        final_model = tuned_model
        final_model_name = 'tuned_random_forest'
        print("Selected tuned Random Forest as final model")
    else:
        final_model = trained_models[best_model_name]
        final_model_name = best_model_name
        print(f"Selected {best_model_name} as final model")

    os.makedirs('models', exist_ok=True)
    joblib.dump(final_model, 'models/final_model.pkl')

    training_results = {
        'final_model': final_model_name,
        'model_comparison': model_results,
        'tuned_rf_mse': float(tuned_mse)
    }

    with open('models/training_results.json', 'w') as f:
        json.dump(training_results, f, indent=2)

    print("Model training complete!")
    return final_model, training_results

if __name__ == "__main__":
    train_pipeline()
