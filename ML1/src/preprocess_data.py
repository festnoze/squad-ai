import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import os

def load_and_preprocess_wine_data():
    """
    Load wine quality datasets, combine them, and preprocess for regression.
    Returns: X_train, X_val, X_test, y_train, y_val, y_test, scaler
    """

    # Load datasets
    print("Loading wine datasets...")
    red_wine = pd.read_csv('data/winequality-red.csv', sep=';')
    white_wine = pd.read_csv('data/winequality-white.csv', sep=';')

    # Add wine type feature (0 = red, 1 = white)
    red_wine['wine_type'] = 0
    white_wine['wine_type'] = 1

    # Combine datasets
    wine_data = pd.concat([red_wine, white_wine], ignore_index=True)

    print(f"Combined dataset shape: {wine_data.shape}")
    print(f"Red wine samples: {len(red_wine)}")
    print(f"White wine samples: {len(white_wine)}")

    # Examine data
    print("\nDataset info:")
    print(wine_data.info())
    print("\nBasic statistics:")
    print(wine_data.describe())

    # Check for missing values
    print(f"\nMissing values: {wine_data.isnull().sum().sum()}")

    # Separate features and target
    feature_columns = [col for col in wine_data.columns if col != 'quality']
    X = wine_data[feature_columns]
    y = wine_data['quality']

    print(f"\nFeatures: {list(X.columns)}")
    print(f"Target distribution:")
    print(y.value_counts().sort_index())

    # Split data: 70% train, 15% validation, 15% test
    # Remove stratification due to classes with too few samples
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.3, random_state=42
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42
    )

    print(f"\nData splits:")
    print(f"Train: {X_train.shape[0]} samples")
    print(f"Validation: {X_val.shape[0]} samples")
    print(f"Test: {X_test.shape[0]} samples")

    # Standardize features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    # Convert back to DataFrames for easier handling
    X_train_scaled = pd.DataFrame(X_train_scaled, columns=X.columns)
    X_val_scaled = pd.DataFrame(X_val_scaled, columns=X.columns)
    X_test_scaled = pd.DataFrame(X_test_scaled, columns=X.columns)

    print("\nFeatures standardized successfully!")
    print(f"Feature means after scaling: {X_train_scaled.mean().round(3).tolist()}")
    print(f"Feature stds after scaling: {X_train_scaled.std().round(3).tolist()}")

    return X_train_scaled, X_val_scaled, X_test_scaled, y_train, y_val, y_test, scaler

