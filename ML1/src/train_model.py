import os
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime
from dotenv import load_dotenv

# ML Libraries
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# Load environment variables
load_dotenv()

class WineQualityNN(nn.Module):
    def __init__(self, input_size, hidden_layers, dropout_rate, activation='relu'):
        super(WineQualityNN, self).__init__()

        # Parse hidden layers
        if isinstance(hidden_layers, str):
            hidden_sizes = [int(x) for x in hidden_layers.split(',')]
        else:
            hidden_sizes = hidden_layers

        # Build network layers
        layers = []
        prev_size = input_size

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            if activation == 'relu':
                layers.append(nn.ReLU())
            elif activation == 'tanh':
                layers.append(nn.Tanh())
            layers.append(nn.Dropout(dropout_rate))
            prev_size = hidden_size

        # Output layer
        layers.append(nn.Linear(prev_size, 1))

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)

class ModelFactory:
    @staticmethod
    def create_model(model_type, **kwargs):
        if model_type == 'linear_regression':
            return LinearRegression()

        elif model_type == 'random_forest':
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

            return WineQualityNN(input_size, hidden_layers, dropout_rate, activation)

        else:
            raise ValueError(f"Unknown model type: {model_type}")

class WineQualityTrainer:
    def __init__(self):
        self.config = self.load_config()
        self.setup_directories()

    def load_config(self):
        config = {
            'model_type': os.getenv('MODEL_TYPE', 'linear_regression'),
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
            'model_name': os.getenv('MODEL_NAME', 'wine_quality_model'),
            'verbose': os.getenv('VERBOSE', 'True').lower() == 'true',
            'data_path': os.getenv('DATA_PATH', 'processed_data'),
            'model_path': os.getenv('MODEL_PATH', 'models'),
            'log_path': os.getenv('LOG_PATH', 'logs')
        }
        return config

    def setup_directories(self):
        os.makedirs(self.config['model_path'], exist_ok=True)
        os.makedirs(self.config['log_path'], exist_ok=True)

    def load_data(self):
        if self.config['verbose']:
            print("Loading preprocessed data...")

        X_train = pd.read_csv(f"{self.config['data_path']}/X_train.csv")
        X_val = pd.read_csv(f"{self.config['data_path']}/X_val.csv")
        X_test = pd.read_csv(f"{self.config['data_path']}/X_test.csv")
        y_train = pd.read_csv(f"{self.config['data_path']}/y_train.csv").squeeze()
        y_val = pd.read_csv(f"{self.config['data_path']}/y_val.csv").squeeze()
        y_test = pd.read_csv(f"{self.config['data_path']}/y_test.csv").squeeze()

        if self.config['verbose']:
            print(f"Data loaded: Train {X_train.shape}, Val {X_val.shape}, Test {X_test.shape}")

        return X_train, X_val, X_test, y_train, y_val, y_test

    def evaluate_model(self, y_true, y_pred, dataset_name=""):
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
            print(f"\n{dataset_name} Metrics:")
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

        # Convert to tensors
        X_train_tensor = torch.FloatTensor(X_train.values)
        y_train_tensor = torch.FloatTensor(y_train.values.reshape(-1, 1))
        X_val_tensor = torch.FloatTensor(X_val.values)
        y_val_tensor = torch.FloatTensor(y_val.values.reshape(-1, 1))

        # Create data loaders
        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        train_loader = DataLoader(train_dataset, batch_size=self.config['batch_size'], shuffle=True)

        # Setup training
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=self.config['learning_rate'])

        # Training loop
        best_val_loss = float('inf')
        patience_counter = 0
        train_losses = []
        val_losses = []

        for epoch in range(self.config['epochs']):
            # Training
            model.train()
            epoch_train_loss = 0
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                epoch_train_loss += loss.item()

            avg_train_loss = epoch_train_loss / len(train_loader)
            train_losses.append(avg_train_loss)

            # Validation
            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val_tensor)
                val_loss = criterion(val_outputs, y_val_tensor).item()
                val_losses.append(val_loss)

            if self.config['verbose'] and (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{self.config['epochs']} - Train Loss: {avg_train_loss:.4f}, Val Loss: {val_loss:.4f}")

            # Early stopping
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
            y_train_pred = model(X_train_tensor).numpy().flatten()
            y_val_pred = model(X_val_tensor).numpy().flatten()

        train_metrics = self.evaluate_model(y_train, y_train_pred, "Training")
        val_metrics = self.evaluate_model(y_val, y_val_pred, "Validation")

        return model, {'train': train_metrics, 'val': val_metrics, 'train_losses': train_losses, 'val_losses': val_losses}

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
            'input_size': X_train.shape[1]
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
                y_test_pred = model(X_test_tensor).numpy().flatten()

        test_metrics = self.evaluate_model(y_test, y_test_pred, "Test")
        metrics['test'] = test_metrics

        # Save model and results
        self.save_model_and_results(model, metrics, self.config['model_name'])

        return model, metrics

