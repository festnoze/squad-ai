import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import os
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, Any
import torch
import torchvision
import torchvision.transforms as transforms


class DatasetConfig:
    """Configuration class for dataset loading and preprocessing"""

    def __init__(self, config_dict: Dict[str, Any]):
        self.name = config_dict.get('name', 'dataset')
        self.loader_type = config_dict.get('loader_type', 'csv')
        self.files = config_dict.get('files', [])
        self.target_column = config_dict.get('target_column', 'target')
        self.separator = config_dict.get('separator', ',')
        self.test_size = config_dict.get('test_size', 0.3)
        self.val_size = config_dict.get('val_size', 0.5)  # From temp split
        self.random_state = config_dict.get('random_state', 42)
        self.scale_features = config_dict.get('scale_features', True)
        self.custom_preprocessing = config_dict.get('custom_preprocessing', None)
        self.feature_engineering = config_dict.get('feature_engineering', {})
        self.exclude_columns = config_dict.get('exclude_columns', [])
        self.include_columns = config_dict.get('include_columns', None)  # If None, include all except excluded
        self.task_type = config_dict.get('task_type', 'regression')
        self.num_classes = config_dict.get('num_classes', 1)

    @classmethod
    def from_file(cls, config_path: str):
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        return cls(config_dict)


class BaseDatasetLoader(ABC):
    """Abstract base class for dataset loaders"""

    def __init__(self, config: DatasetConfig):
        self.config = config
        self.scaler = None

    @abstractmethod
    def load_raw_data(self) -> pd.DataFrame:
        """Load raw data from source files"""
        pass

    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply basic preprocessing"""
        # Check for missing values
        missing_values = data.isnull().sum().sum()
        print(f"Missing values: {missing_values}")

        if missing_values > 0:
            print("Handling missing values...")
            # Simple strategy: drop rows with missing values
            # Could be made configurable
            data = data.dropna()
            print(f"Shape after dropping missing values: {data.shape}")

        return data

    def feature_engineering(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply feature engineering transformations"""
        for feature_name, transformation in self.config.feature_engineering.items():
            if transformation['type'] == 'combine_datasets':
                # Handle dataset combination (like wine red/white)
                data[feature_name] = transformation['values']
            elif transformation['type'] == 'categorical_encode':
                # Handle categorical encoding
                data[feature_name] = data[transformation['source_column']].map(transformation['mapping'])
            # Add more transformation types as needed
        return data

    def select_features(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Select features and target variable"""
        # Remove excluded columns
        for col in self.config.exclude_columns:
            if col in data.columns:
                data = data.drop(columns=[col])

        # Select included columns if specified
        if self.config.include_columns:
            available_cols = [col for col in self.config.include_columns if col in data.columns]
            data = data[available_cols + [self.config.target_column]]

        # Separate features and target
        if self.config.target_column not in data.columns:
            raise ValueError(f"Target column '{self.config.target_column}' not found in data")

        X = data.drop(columns=[self.config.target_column])
        y = data[self.config.target_column]

        return X, y

    def split_data(self, X: pd.DataFrame, y: pd.Series) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
        """Split data into train, validation, and test sets"""
        # First split: train + val / test
        X_train_val, X_test, y_train_val, y_test = train_test_split(
            X, y, test_size=self.config.test_size, random_state=self.config.random_state
        )

        # Second split: train / val
        X_train, X_val, y_train, y_val = train_test_split(
            X_train_val, y_train_val, test_size=self.config.val_size, random_state=self.config.random_state
        )

        return X_train, X_val, X_test, y_train, y_val, y_test

    def scale_features(self, X_train: pd.DataFrame, X_val: pd.DataFrame, X_test: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Scale features using StandardScaler"""
        if not self.config.scale_features:
            return X_train, X_val, X_test

        self.scaler = StandardScaler()
        X_train_scaled = pd.DataFrame(
            self.scaler.fit_transform(X_train),
            columns=X_train.columns,
            index=X_train.index
        )
        X_val_scaled = pd.DataFrame(
            self.scaler.transform(X_val),
            columns=X_val.columns,
            index=X_val.index
        )
        X_test_scaled = pd.DataFrame(
            self.scaler.transform(X_test),
            columns=X_test.columns,
            index=X_test.index
        )

        return X_train_scaled, X_val_scaled, X_test_scaled

    def load_and_preprocess(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, Optional[StandardScaler]]:
        """Complete pipeline: load, preprocess, and split data"""
        print(f"Loading {self.config.name} dataset...")

        # Load raw data
        data = self.load_raw_data()
        print(f"Raw data shape: {data.shape}")

        # Apply preprocessing
        data = self.preprocess_data(data)

        # Apply feature engineering
        data = self.feature_engineering(data)

        # Select features and target
        X, y = self.select_features(data)
        print(f"Features: {list(X.columns)}")
        print(f"Target distribution:\n{y.value_counts().sort_index()}")

        # Split data
        X_train, X_val, X_test, y_train, y_val, y_test = self.split_data(X, y)
        print(f"Data splits - Train: {X_train.shape[0]}, Val: {X_val.shape[0]}, Test: {X_test.shape[0]}")

        # Scale features
        X_train_scaled, X_val_scaled, X_test_scaled = self.scale_features(X_train, X_val, X_test)

        if self.config.scale_features:
            print("Features standardized successfully!")
            print(f"Feature means after scaling: {X_train_scaled.mean().round(3).tolist()}")
            print(f"Feature stds after scaling: {X_train_scaled.std().round(3).tolist()}")

        return X_train_scaled, X_val_scaled, X_test_scaled, y_train, y_val, y_test, self.scaler


class CSVDatasetLoader(BaseDatasetLoader):
    """Generic CSV dataset loader"""

    def load_raw_data(self) -> pd.DataFrame:
        """Load data from CSV files"""
        if not self.config.files:
            raise ValueError("No files specified in configuration")

        dataframes = []
        for file_config in self.config.files:
            file_path = file_config['path']
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            df = pd.read_csv(file_path, sep=self.config.separator)

            # Add any file-specific columns
            if 'add_columns' in file_config:
                for col_name, col_value in file_config['add_columns'].items():
                    df[col_name] = col_value

            dataframes.append(df)
            print(f"Loaded {file_path}: {df.shape}")

        # Combine all dataframes
        if len(dataframes) == 1:
            combined_data = dataframes[0]
        else:
            combined_data = pd.concat(dataframes, ignore_index=True)

        print(f"Combined dataset shape: {combined_data.shape}")
        return combined_data


class WineQualityDatasetLoader(CSVDatasetLoader):
    """Specialized loader for wine quality dataset (backwards compatibility)"""

    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Wine-specific preprocessing"""
        data = super().preprocess_data(data)

        # Display wine-specific info
        if 'wine_type' in data.columns:
            print("\nWine dataset info:")
            print(f"Red wine samples: {(data['wine_type'] == 0).sum()}")
            print(f"White wine samples: {(data['wine_type'] == 1).sum()}")

        print("\nDataset info:")
        print(data.info())
        print("\nBasic statistics:")
        print(data.describe())

        return data


class MNISTDatasetLoader(BaseDatasetLoader):
    """Specialized loader for MNIST handwritten digit dataset"""

    def load_raw_data(self) -> pd.DataFrame:
        """Load MNIST data using torchvision and convert to DataFrame"""
        print("Downloading MNIST dataset...")

        # Download MNIST data
        transform = transforms.Compose([transforms.ToTensor()])

        # Create data directory if it doesn't exist
        if self.config.files and 'path' in self.config.files[0]:
            data_dir = self.config.files[0]['path']
        else:
            data_dir = 'data'
        os.makedirs(data_dir, exist_ok=True)

        # Load training and test sets
        train_dataset = torchvision.datasets.MNIST(
            root=data_dir, train=True, download=True, transform=transform
        )
        test_dataset = torchvision.datasets.MNIST(
            root=data_dir, train=False, download=True, transform=transform
        )

        # Convert to numpy arrays
        train_data = []
        train_labels = []
        for image, label in train_dataset:
            # Flatten 28x28 image to 784 features
            flattened_image = image.numpy().flatten()
            train_data.append(flattened_image)
            train_labels.append(label)

        test_data = []
        test_labels = []
        for image, label in test_dataset:
            flattened_image = image.numpy().flatten()
            test_data.append(flattened_image)
            test_labels.append(label)

        # Create DataFrames
        train_df = pd.DataFrame(train_data)
        train_df[self.config.target_column] = train_labels
        train_df['split'] = 'train'

        test_df = pd.DataFrame(test_data)
        test_df[self.config.target_column] = test_labels
        test_df['split'] = 'test'

        # Combine train and test for unified preprocessing
        combined_df = pd.concat([train_df, test_df], ignore_index=True)

        print(f"MNIST dataset loaded: {len(train_dataset)} train + {len(test_dataset)} test samples")
        print(f"Image dimensions: 28x28 = 784 features")
        print(f"Classes: {sorted(set(train_labels + test_labels))}")

        return combined_df

    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """MNIST-specific preprocessing with optimizations"""
        data = super().preprocess_data(data)

        if data is not None:
            print("\nMNIST dataset info:")
            print(f"Total samples: {len(data)}")
            print(f"Features: 784 (28x28 pixels)")
            print(f"Classes: {sorted(data[self.config.target_column].unique())}")
            print(f"Class distribution:")
            print(data[self.config.target_column].value_counts().sort_index())

            # MNIST-specific preprocessing optimizations
            pixel_columns = [col for col in data.columns if col not in [self.config.target_column, 'split']]

            # Normalize pixel values to [0, 1] range (they're already 0-255)
            print("Normalizing pixel values to [0, 1] range...")
            data[pixel_columns] = data[pixel_columns] / 255.0

            # Remove completely black pixels (columns with all zeros) to reduce dimensionality
            zero_columns = data[pixel_columns].columns[(data[pixel_columns] == 0).all()]
            if len(zero_columns) > 0:
                print(f"Removing {len(zero_columns)} always-zero pixel columns...")
                data = data.drop(columns=zero_columns)

            print(f"Final feature count: {len([col for col in data.columns if col not in [self.config.target_column, 'split']])}")

        return data

    def split_data(self, X: pd.DataFrame, y: pd.Series) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
        """Custom split for MNIST using predefined train/test split"""
        # Get the original split column
        split_info = X['split'] if 'split' in X.columns else None

        # Remove split column from features
        if 'split' in X.columns:
            X = X.drop(columns=['split'])

        if split_info is not None:
            # Use predefined MNIST train/test split
            train_mask = split_info == 'train'
            test_mask = split_info == 'test'

            X_train_full = X[train_mask].reset_index(drop=True)
            y_train_full = y[train_mask].reset_index(drop=True)
            X_test = X[test_mask].reset_index(drop=True)
            y_test = y[test_mask].reset_index(drop=True)

            # Split training data into train and validation
            X_train, X_val, y_train, y_val = train_test_split(
                X_train_full, y_train_full,
                test_size=self.config.val_size,
                random_state=self.config.random_state,
                stratify=y_train_full  # Stratify for balanced validation split
            )
        else:
            # Fallback to regular splitting
            X_train, X_val, X_test, y_train, y_val, y_test = super().split_data(X, y)

        return X_train, X_val, X_test, y_train, y_val, y_test


def create_dataset_loader(config_path_or_dict) -> BaseDatasetLoader:
    """Factory function to create appropriate dataset loader"""
    if isinstance(config_path_or_dict, str):
        config = DatasetConfig.from_file(config_path_or_dict)
    else:
        config = DatasetConfig(config_path_or_dict)

    # Determine loader type based on config
    loader_type = config.loader_type

    if loader_type == 'wine_quality':
        return WineQualityDatasetLoader(config)
    elif loader_type == 'mnist':
        return MNISTDatasetLoader(config)
    else:
        return CSVDatasetLoader(config)