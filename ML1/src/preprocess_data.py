import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import os
from .dataset_loader import create_dataset_loader, DatasetConfig

def load_and_preprocess_data(config_path_or_dict=None):
    """
    Load and preprocess any dataset using configuration.
    Args:
        config_path_or_dict: Path to JSON config file or dict with config
    Returns: X_train, X_val, X_test, y_train, y_val, y_test, scaler
    """
    # Default to wine quality dataset for backwards compatibility
    if config_path_or_dict is None:
        config_path_or_dict = 'configs/wine_quality.json'

    # Create dataset loader
    loader = create_dataset_loader(config_path_or_dict)

    # Load and preprocess data
    return loader.load_and_preprocess()

def load_and_preprocess_wine_data():
    """
    Legacy function for backwards compatibility.
    Load wine quality datasets, combine them, and preprocess for regression.
    Returns: X_train, X_val, X_test, y_train, y_val, y_test, scaler
    """
    return load_and_preprocess_data('configs/wine_quality.json')

