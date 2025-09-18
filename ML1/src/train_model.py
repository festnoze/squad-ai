import os
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime
from dotenv import load_dotenv

# ML Libraries
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, accuracy_score, classification_report, confusion_matrix
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# Load environment variables
load_dotenv()

class MLNeuralNetwork(nn.Module):
    def __init__(self, input_size, hidden_layers, dropout_rate, activation='relu', task_type='regression', num_classes=1):
        super(MLNeuralNetwork, self).__init__()

        self.task_type = task_type
        self.input_size = input_size

        # Parse hidden layers
        if isinstance(hidden_layers, str):
            hidden_sizes = [int(x) for x in hidden_layers.split(',')]
        else:
            hidden_sizes = hidden_layers

        # MNIST-specific optimizations
        if input_size > 500:  # Likely MNIST (784 features)
            # Add batch normalization and better architecture for image data
            self.network = self._build_mnist_network(input_size, hidden_sizes, dropout_rate, activation, num_classes)
        else:
            # Regular network for smaller datasets
            self.network = self._build_regular_network(input_size, hidden_sizes, dropout_rate, activation, task_type, num_classes)

    def _build_mnist_network(self, input_size, hidden_sizes, dropout_rate, activation, num_classes):
        """Build optimized network for MNIST-like image data"""
        layers = []

        # Input layer with batch normalization
        layers.append(nn.Linear(input_size, hidden_sizes[0]))
        layers.append(nn.BatchNorm1d(hidden_sizes[0]))

        if activation == 'relu':
            layers.append(nn.ReLU())
        elif activation == 'tanh':
            layers.append(nn.Tanh())
        elif activation == 'leaky_relu':
            layers.append(nn.LeakyReLU(0.1))

        layers.append(nn.Dropout(dropout_rate))

        # Hidden layers with batch normalization
        for i in range(1, len(hidden_sizes)):
            layers.append(nn.Linear(hidden_sizes[i-1], hidden_sizes[i]))
            layers.append(nn.BatchNorm1d(hidden_sizes[i]))

            if activation == 'relu':
                layers.append(nn.ReLU())
            elif activation == 'tanh':
                layers.append(nn.Tanh())
            elif activation == 'leaky_relu':
                layers.append(nn.LeakyReLU(0.1))

            layers.append(nn.Dropout(dropout_rate))

        # Output layer
        if self.task_type == 'classification':
            layers.append(nn.Linear(hidden_sizes[-1], num_classes))
        else:
            layers.append(nn.Linear(hidden_sizes[-1], 1))

        return nn.Sequential(*layers)

    def _build_regular_network(self, input_size, hidden_sizes, dropout_rate, activation, task_type, num_classes):
        """Build regular network for non-image data"""
        layers = []
        prev_size = input_size

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            if activation == 'relu':
                layers.append(nn.ReLU())
            elif activation == 'tanh':
                layers.append(nn.Tanh())
            elif activation == 'leaky_relu':
                layers.append(nn.LeakyReLU(0.1))
            layers.append(nn.Dropout(dropout_rate))
            prev_size = hidden_size

        # Output layer based on task type
        if task_type == 'classification':
            layers.append(nn.Linear(prev_size, num_classes))
        else:
            layers.append(nn.Linear(prev_size, 1))

        return nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)

class ModelFactory:
    @staticmethod
    def create_model(model_type, **kwargs):
        task_type = kwargs.get('task_type', 'regression')

        if model_type == 'linear_regression':
            if task_type == 'classification':
                return LogisticRegression(
                    random_state=kwargs.get('random_seed', 42),
                    max_iter=1000
                )
            else:
                return LinearRegression()

        elif model_type == 'random_forest':
            if task_type == 'classification':
                return RandomForestClassifier(
                    n_estimators=kwargs.get('n_estimators', 100),
                    max_depth=kwargs.get('max_depth'),
                    min_samples_split=kwargs.get('min_samples_split', 2),
                    min_samples_leaf=kwargs.get('min_samples_leaf', 1),
                    random_state=kwargs.get('random_seed', 42)
                )
            else:
                return RandomForestRegressor(
                    n_estimators=kwargs.get('n_estimators', 100),
                    max_depth=kwargs.get('max_depth'),
                    min_samples_split=kwargs.get('min_samples_split', 2),
                    min_samples_leaf=kwargs.get('min_samples_leaf', 1),
                    random_state=kwargs.get('random_seed', 42)
                )

        elif model_type == 'neural_network':
            input_size = kwargs.get('input_size')
            hidden_layers = kwargs.get('hidden_layers', '64,32')
            dropout_rate = kwargs.get('dropout_rate', 0.2)
            activation = kwargs.get('activation', 'relu')
            num_classes = kwargs.get('num_classes', 1)

            return MLNeuralNetwork(
                input_size, hidden_layers, dropout_rate, activation, task_type, num_classes
            )

        else:
            raise ValueError(f"Unknown model type: {model_type}")

class MLTrainer:
    def __init__(self):
        self.config = self.load_config()
        self.setup_directories()

    def load_config(self):
        config = {
            'model_type': os.getenv('MODEL_TYPE', 'linear_regression'),
            'task_type': os.getenv('TASK_TYPE', 'regression'),
            'num_classes': int(os.getenv('NUM_CLASSES', 1)),
            'learning_rate': float(os.getenv('LEARNING_RATE', 0.001)),
            'epochs': int(os.getenv('EPOCHS', 100)),
            'batch_size': int(os.getenv('BATCH_SIZE', 32)),
            'validation_patience': int(os.getenv('VALIDATION_PATIENCE', 10)),
            'n_estimators': int(os.getenv('N_ESTIMATORS', 100)),
            'max_depth': None if os.getenv('MAX_DEPTH') == 'None' else int(os.getenv('MAX_DEPTH', 10)),
            'min_samples_split': int(os.getenv('MIN_SAMPLES_SPLIT', 2)),
            'min_samples_leaf': int(os.getenv('MIN_SAMPLES_LEAF', 1)),
            'hidden_layers': os.getenv('HIDDEN_LAYERS', '64,32'),
            'dropout_rate': float(os.getenv('DROPOUT_RATE', 0.2)),
            'activation': os.getenv('ACTIVATION', 'relu'),
            'random_seed': int(os.getenv('RANDOM_SEED', 42)),
            'save_model': os.getenv('SAVE_MODEL', 'True').lower() == 'true',
            'model_name': os.getenv('MODEL_NAME', 'ml_model'),
            'verbose': os.getenv('VERBOSE', 'True').lower() == 'true',
            'data_path': os.getenv('DATA_PATH', 'processed_data'),
            'model_path': os.getenv('MODEL_PATH', 'models'),
            'log_path': os.getenv('LOG_PATH', 'logs'),
            'dataset_config': os.getenv('DATASET_CONFIG', 'configs/wine_quality.json')
        }
        return config

    def setup_directories(self):
        os.makedirs(self.config['model_path'], exist_ok=True)
        os.makedirs(self.config['log_path'], exist_ok=True)

    def load_data(self):
        if self.config['verbose']:
            print("Loading preprocessed data...")

        # Try to load from preprocessed files first
        try:
            X_train = pd.read_csv(f"{self.config['data_path']}/X_train.csv")
            X_val = pd.read_csv(f"{self.config['data_path']}/X_val.csv")
            X_test = pd.read_csv(f"{self.config['data_path']}/X_test.csv")
            y_train = pd.read_csv(f"{self.config['data_path']}/y_train.csv").squeeze()
            y_val = pd.read_csv(f"{self.config['data_path']}/y_val.csv").squeeze()
            y_test = pd.read_csv(f"{self.config['data_path']}/y_test.csv").squeeze()

            if self.config['verbose']:
                print(f"Data loaded from files: Train {X_train.shape}, Val {X_val.shape}, Test {X_test.shape}")

            return X_train, X_val, X_test, y_train, y_val, y_test

        except FileNotFoundError:
            if self.config['verbose']:
                print("Preprocessed data not found. Loading and preprocessing from source...")

            # Import here to avoid circular imports
            from .preprocess_data import load_and_preprocess_data
            from .dataset_loader import DatasetConfig

            # Load dataset config to extract task info
            dataset_config = DatasetConfig.from_file(self.config['dataset_config'])

            # Update config with dataset-specific settings
            if hasattr(dataset_config, 'task_type'):
                self.config['task_type'] = dataset_config.task_type
            if hasattr(dataset_config, 'num_classes'):
                self.config['num_classes'] = dataset_config.num_classes

            # Load data using generalized loader
            X_train, X_val, X_test, y_train, y_val, y_test, scaler = load_and_preprocess_data(
                self.config['dataset_config']
            )

            if self.config['verbose']:
                print(f"Data loaded and preprocessed: Train {X_train.shape}, Val {X_val.shape}, Test {X_test.shape}")

            return X_train, X_val, X_test, y_train, y_val, y_test

    def evaluate_model(self, y_true, y_pred, dataset_name=""):
        if self.config['task_type'] == 'classification':
            # Classification metrics
            accuracy = accuracy_score(y_true, y_pred)

            metrics = {
                'accuracy': accuracy,
                'classification_report': classification_report(y_true, y_pred, output_dict=True),
                'confusion_matrix': confusion_matrix(y_true, y_pred).tolist()
            }

            if self.config['verbose']:
                print(f"\n{dataset_name} Classification Metrics:")
                print(f"  Accuracy: {accuracy:.4f}")
                print(f"  Classification Report:")
                print(classification_report(y_true, y_pred))

        else:
            # Regression metrics
            mse = mean_squared_error(y_true, y_pred)
            mae = mean_absolute_error(y_true, y_pred)
            r2 = r2_score(y_true, y_pred)
            rmse = np.sqrt(mse)

            metrics = {
                'mse': mse,
                'mae': mae,
                'rmse': rmse,
                'r2': r2
            }

            if self.config['verbose']:
                print(f"\n{dataset_name} Regression Metrics:")
                print(f"  MSE:  {mse:.4f}")
                print(f"  MAE:  {mae:.4f}")
                print(f"  RMSE: {rmse:.4f}")
                print(f"  R²:   {r2:.4f}")

        return metrics

    def train_sklearn_model(self, model, X_train, y_train, X_val, y_val):
        if self.config['verbose']:
            print(f"Training {self.config['model_type']} model...")

        # Train model
        model.fit(X_train, y_train)

        # Predictions
        y_train_pred = model.predict(X_train)
        y_val_pred = model.predict(X_val)

        # Evaluate
        train_metrics = self.evaluate_model(y_train, y_train_pred, "Training")
        val_metrics = self.evaluate_model(y_val, y_val_pred, "Validation")

        # Add training history for visualization (single point for sklearn models)
        if self.config['task_type'] == 'classification':
            history = {
                'train_losses': [1 - train_metrics['accuracy']],  # Use error rate as "loss"
                'val_losses': [1 - val_metrics['accuracy']],
                'train_accuracy': [train_metrics['accuracy']],
                'val_accuracy': [val_metrics['accuracy']]
            }
        else:
            history = {
                'train_losses': [train_metrics['mse']],
                'val_losses': [val_metrics['mse']],
                'train_r2': [train_metrics['r2']],
                'val_r2': [val_metrics['r2']]
            }

        return model, {'train': train_metrics, 'val': val_metrics, **history}

    def train_pytorch_model(self, model, X_train, y_train, X_val, y_val):
        if self.config['verbose']:
            print(f"Training Neural Network model...")
            print(f"Input size: {X_train.shape[1]}, Task: {self.config['task_type']}")

        # Convert to tensors
        X_train_tensor = torch.FloatTensor(X_train.values)
        X_val_tensor = torch.FloatTensor(X_val.values)

        if self.config['task_type'] == 'classification':
            y_train_tensor = torch.LongTensor(y_train.values)  # Classification labels
            y_val_tensor = torch.LongTensor(y_val.values)
        else:
            y_train_tensor = torch.FloatTensor(y_train.values.reshape(-1, 1))  # Regression targets
            y_val_tensor = torch.FloatTensor(y_val.values.reshape(-1, 1))

        # MNIST-specific optimizations
        batch_size = self.config['batch_size']
        if X_train.shape[1] > 500:  # Likely MNIST
            batch_size = min(256, batch_size)  # Larger batches for MNIST
            print(f"Using optimized batch size for image data: {batch_size}")

        # Create data loaders with better settings for MNIST
        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,  # Keep 0 for compatibility
            pin_memory=False  # Set False for CPU training
        )

        # Setup training with better optimizer for MNIST
        if self.config['task_type'] == 'classification':
            criterion = nn.CrossEntropyLoss()
        else:
            criterion = nn.MSELoss()

        # Use different optimizers based on dataset size
        if X_train.shape[1] > 500:  # MNIST-like datasets
            optimizer = optim.AdamW(
                model.parameters(),
                lr=self.config['learning_rate'],
                weight_decay=1e-4  # L2 regularization
            )
            # Learning rate scheduler for better convergence
            scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                optimizer, mode='min', factor=0.5, patience=5
            )
        else:
            optimizer = optim.Adam(model.parameters(), lr=self.config['learning_rate'])
            scheduler = None

        # Training loop
        best_val_loss = float('inf')
        best_val_accuracy = 0.0
        patience_counter = 0
        train_losses = []
        val_losses = []
        train_accuracies = []
        val_accuracies = []

        print(f"Starting training for {self.config['epochs']} epochs...")

        for epoch in range(self.config['epochs']):
            # Training
            model.train()
            epoch_train_loss = 0
            correct_train = 0
            total_train = 0

            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()

                # Gradient clipping for stability
                if X_train.shape[1] > 500:  # MNIST-like datasets
                    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

                optimizer.step()
                epoch_train_loss += loss.item()

                # Calculate training accuracy for classification
                if self.config['task_type'] == 'classification':
                    _, predicted = torch.max(outputs.data, 1)
                    total_train += batch_y.size(0)
                    correct_train += (predicted == batch_y).sum().item()

            avg_train_loss = epoch_train_loss / len(train_loader)
            train_losses.append(avg_train_loss)

            if self.config['task_type'] == 'classification':
                train_accuracy = correct_train / total_train
                train_accuracies.append(train_accuracy)

            # Validation
            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val_tensor)
                val_loss = criterion(val_outputs, y_val_tensor).item()
                val_losses.append(val_loss)

                # Calculate validation accuracy for classification
                val_accuracy = 0.0
                if self.config['task_type'] == 'classification':
                    _, val_predicted = torch.max(val_outputs, 1)
                    val_accuracy = (val_predicted == y_val_tensor).float().mean().item()
                    val_accuracies.append(val_accuracy)

            # Learning rate scheduling
            if scheduler is not None:
                scheduler.step(val_loss)

            # Progress reporting
            if self.config['verbose'] and (epoch + 1) % 10 == 0:
                if self.config['task_type'] == 'classification':
                    print(f"Epoch {epoch+1}/{self.config['epochs']} - Train Loss: {avg_train_loss:.4f}, Val Loss: {val_loss:.4f}, Train Acc: {train_accuracy:.4f}, Val Acc: {val_accuracy:.4f}")
                else:
                    print(f"Epoch {epoch+1}/{self.config['epochs']} - Train Loss: {avg_train_loss:.4f}, Val Loss: {val_loss:.4f}")

            # Early stopping (use accuracy for classification, loss for regression)
            if self.config['task_type'] == 'classification':
                if val_accuracy > best_val_accuracy:
                    best_val_accuracy = val_accuracy
                    patience_counter = 0
                    best_model_state = model.state_dict().copy()
                else:
                    patience_counter += 1
            else:
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    best_model_state = model.state_dict().copy()
                else:
                    patience_counter += 1

            if patience_counter >= self.config['validation_patience']:
                if self.config['verbose']:
                    print(f"Early stopping at epoch {epoch+1}")
                break

        # Load best model
        model.load_state_dict(best_model_state)

        # Final evaluation
        model.eval()
        with torch.no_grad():
            if self.config['task_type'] == 'classification':
                train_outputs = model(X_train_tensor)
                val_outputs = model(X_val_tensor)
                y_train_pred = torch.argmax(train_outputs, dim=1).numpy()
                y_val_pred = torch.argmax(val_outputs, dim=1).numpy()
            else:
                y_train_pred = model(X_train_tensor).numpy().flatten()
                y_val_pred = model(X_val_tensor).numpy().flatten()

        train_metrics = self.evaluate_model(y_train, y_train_pred, "Training")
        val_metrics = self.evaluate_model(y_val, y_val_pred, "Validation")

        # Prepare training history
        history = {
            'train_losses': train_losses,
            'val_losses': val_losses
        }

        if self.config['task_type'] == 'classification':
            history.update({
                'train_accuracies': train_accuracies,
                'val_accuracies': val_accuracies
            })

        return model, {'train': train_metrics, 'val': val_metrics, **history}

    def save_model_and_results(self, model, metrics, model_name):
        if not self.config['save_model']:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_dir = f"{self.config['model_path']}/{model_name}_{timestamp}"
        os.makedirs(model_dir, exist_ok=True)

        # Save model
        if self.config['model_type'] in ['linear_regression', 'random_forest']:
            pickle.dump(model, open(f"{model_dir}/model.pkl", 'wb'))
        elif self.config['model_type'] == 'neural_network':
            torch.save(model.state_dict(), f"{model_dir}/model.pth")

        # Save config and metrics
        with open(f"{model_dir}/config.json", 'w') as f:
            json.dump(self.config, f, indent=2)

        with open(f"{model_dir}/metrics.json", 'w') as f:
            json.dump(metrics, f, indent=2)

        if self.config['verbose']:
            print(f"Model saved to: {model_dir}")

    def train(self):
        # Load data
        X_train, X_val, X_test, y_train, y_val, y_test = self.load_data()

        # Create model
        model_kwargs = {
            'n_estimators': self.config['n_estimators'],
            'max_depth': self.config['max_depth'],
            'min_samples_split': self.config['min_samples_split'],
            'min_samples_leaf': self.config['min_samples_leaf'],
            'hidden_layers': self.config['hidden_layers'],
            'dropout_rate': self.config['dropout_rate'],
            'activation': self.config['activation'],
            'random_seed': self.config['random_seed'],
            'input_size': X_train.shape[1],
            'task_type': self.config['task_type'],
            'num_classes': self.config['num_classes']
        }

        model = ModelFactory.create_model(self.config['model_type'], **model_kwargs)

        # Train model
        if self.config['model_type'] in ['linear_regression', 'random_forest']:
            model, metrics = self.train_sklearn_model(model, X_train, y_train, X_val, y_val)
        elif self.config['model_type'] == 'neural_network':
            model, metrics = self.train_pytorch_model(model, X_train, y_train, X_val, y_val)

        # Test evaluation
        if self.config['model_type'] in ['linear_regression', 'random_forest']:
            y_test_pred = model.predict(X_test)
        else:
            model.eval()
            with torch.no_grad():
                X_test_tensor = torch.FloatTensor(X_test.values)
                if self.config['task_type'] == 'classification':
                    test_outputs = model(X_test_tensor)
                    y_test_pred = torch.argmax(test_outputs, dim=1).numpy()
                else:
                    y_test_pred = model(X_test_tensor).numpy().flatten()

        test_metrics = self.evaluate_model(y_test, y_test_pred, "Test")
        metrics['test'] = test_metrics

        # Save model and results
        self.save_model_and_results(model, metrics, self.config['model_name'])

        return model, metrics

