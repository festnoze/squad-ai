import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import pickle
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from src.preprocess_data import load_and_preprocess_wine_data
from src.train_model import WineQualityTrainer
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import time

st.set_page_config(
    page_title="🍷 Wine Quality ML Pipeline",
    page_icon="🍷",
    layout="wide"
)

def load_model_data():
    """Load all available models and their data"""
    models_data = {}

    if not os.path.exists('models'):
        return models_data

    for model_dir in os.listdir('models'):
        model_path = os.path.join('models', model_dir)
        if os.path.isdir(model_path):
            config_path = os.path.join(model_path, 'config.json')
            metrics_path = os.path.join(model_path, 'metrics.json')

            if os.path.exists(config_path) and os.path.exists(metrics_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                with open(metrics_path, 'r') as f:
                    metrics = json.load(f)

                models_data[model_dir] = {
                    'config': config,
                    'metrics': metrics,
                    'path': model_path
                }

    return models_data

def load_test_data():
    """Load test data if available"""
    try:
        X_test = pd.read_csv('processed_data/X_test.csv')
        y_test = pd.read_csv('processed_data/y_test.csv').squeeze()
        return X_test, y_test
    except:
        return None, None

def plot_training_history(metrics, model_name):
    """Plot training history with epoch selection"""
    if 'train_losses' not in metrics or 'val_losses' not in metrics:
        st.warning("No training history available for this model")
        return

    train_losses = metrics['train_losses']
    val_losses = metrics['val_losses']
    epochs = list(range(1, len(train_losses) + 1))

    # Epoch selection slider
    if len(epochs) > 1:
        max_epoch = st.slider(
            "Select epoch to view progress up to:",
            min_value=1,
            max_value=len(epochs),
            value=len(epochs),
            key=f"epoch_slider_{model_name}"
        )

        # Slice data up to selected epoch
        epochs_slice = epochs[:max_epoch]
        train_slice = train_losses[:max_epoch]
        val_slice = val_losses[:max_epoch]
    else:
        epochs_slice = epochs
        train_slice = train_losses
        val_slice = val_losses

    # Create interactive plot
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=epochs_slice,
        y=train_slice,
        mode='lines+markers',
        name='Training Loss',
        line=dict(color='blue', width=2),
        marker=dict(size=4)
    ))

    fig.add_trace(go.Scatter(
        x=epochs_slice,
        y=val_slice,
        mode='lines+markers',
        name='Validation Loss',
        line=dict(color='red', width=2),
        marker=dict(size=4)
    ))

    fig.update_layout(
        title=f'Training Progress - {model_name}',
        xaxis_title='Epoch',
        yaxis_title='Loss (MSE)',
        hovermode='x unified',
        template='plotly_white'
    )

    st.plotly_chart(fig, use_container_width=True)

    # Show current epoch metrics
    if len(epochs_slice) > 0:
        current_epoch = max_epoch
        current_train_loss = train_slice[-1]
        current_val_loss = val_slice[-1]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Current Epoch", current_epoch)
        with col2:
            st.metric("Training Loss", f"{current_train_loss:.4f}")
        with col3:
            st.metric("Validation Loss", f"{current_val_loss:.4f}")

def plot_linear_regression_analysis(model_path, X_test, y_test):
    """Visualize linear regression model analysis"""
    try:
        # Load model
        model_file = os.path.join(model_path, 'model.pkl')
        with open(model_file, 'rb') as f:
            model = pickle.load(f)

        # Make predictions
        y_pred = model.predict(X_test)

        # Create subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[
                'Actual vs Predicted',
                'Residuals Plot',
                'Feature Importance',
                'Prediction Distribution'
            ]
        )

        # 1. Actual vs Predicted
        fig.add_trace(
            go.Scatter(
                x=y_test,
                y=y_pred,
                mode='markers',
                name='Predictions',
                marker=dict(color='blue', size=5, opacity=0.6)
            ),
            row=1, col=1
        )

        # Perfect prediction line
        min_val = min(min(y_test), min(y_pred))
        max_val = max(max(y_test), max(y_pred))
        fig.add_trace(
            go.Scatter(
                x=[min_val, max_val],
                y=[min_val, max_val],
                mode='lines',
                name='Perfect Prediction',
                line=dict(color='red', dash='dash')
            ),
            row=1, col=1
        )

        # 2. Residuals Plot
        residuals = y_test - y_pred
        fig.add_trace(
            go.Scatter(
                x=y_pred,
                y=residuals,
                mode='markers',
                name='Residuals',
                marker=dict(color='green', size=5, opacity=0.6)
            ),
            row=1, col=2
        )

        # Zero line for residuals
        fig.add_trace(
            go.Scatter(
                x=[min(y_pred), max(y_pred)],
                y=[0, 0],
                mode='lines',
                name='Zero Line',
                line=dict(color='red', dash='dash')
            ),
            row=1, col=2
        )

        # 3. Feature Importance (coefficients)
        if hasattr(model, 'coef_'):
            feature_names = X_test.columns
            coefficients = model.coef_

            fig.add_trace(
                go.Bar(
                    x=feature_names,
                    y=np.abs(coefficients),
                    name='Feature Importance',
                    marker=dict(color='purple')
                ),
                row=2, col=1
            )

        # 4. Prediction Distribution
        fig.add_trace(
            go.Histogram(
                x=y_test,
                name='Actual',
                opacity=0.7,
                marker=dict(color='blue')
            ),
            row=2, col=2
        )

        fig.add_trace(
            go.Histogram(
                x=y_pred,
                name='Predicted',
                opacity=0.7,
                marker=dict(color='red')
            ),
            row=2, col=2
        )

        fig.update_layout(
            height=800,
            showlegend=True,
            title_text="Linear Regression Analysis"
        )

        # Update axis labels
        fig.update_xaxes(title_text="Actual Quality", row=1, col=1)
        fig.update_yaxes(title_text="Predicted Quality", row=1, col=1)
        fig.update_xaxes(title_text="Predicted Quality", row=1, col=2)
        fig.update_yaxes(title_text="Residuals", row=1, col=2)
        fig.update_xaxes(title_text="Features", row=2, col=1)
        fig.update_yaxes(title_text="Coefficient Magnitude", row=2, col=1)
        fig.update_xaxes(title_text="Quality Score", row=2, col=2)
        fig.update_yaxes(title_text="Frequency", row=2, col=2)

        st.plotly_chart(fig, use_container_width=True)

        # Metrics
        mse = mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("R² Score", f"{r2:.4f}")
        with col2:
            st.metric("RMSE", f"{np.sqrt(mse):.4f}")
        with col3:
            st.metric("MAE", f"{mae:.4f}")

    except Exception as e:
        st.error(f"Error analyzing linear regression: {e}")

def process_data_streamlit():
    """Streamlit interface for data processing"""
    st.header("🔄 Data Processing")

    st.markdown("Process and prepare wine quality datasets for training.")

    if st.button("Process Data", type="primary"):
        with st.spinner("Processing data..."):
            try:
                # Run preprocessing
                X_train, X_val, X_test, y_train, y_val, y_test, scaler = load_and_preprocess_wine_data()

                # Save preprocessed data
                os.makedirs('processed_data', exist_ok=True)
                X_train.to_csv('processed_data/X_train.csv', index=False)
                X_val.to_csv('processed_data/X_val.csv', index=False)
                X_test.to_csv('processed_data/X_test.csv', index=False)
                y_train.to_csv('processed_data/y_train.csv', index=False)
                y_val.to_csv('processed_data/y_val.csv', index=False)
                y_test.to_csv('processed_data/y_test.csv', index=False)

                st.success("✅ Data processing completed!")

                # Show data info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Training samples", X_train.shape[0])
                with col2:
                    st.metric("Validation samples", X_val.shape[0])
                with col3:
                    st.metric("Test samples", X_test.shape[0])

                st.info("📁 Processed data saved to 'processed_data/' folder")

            except Exception as e:
                st.error(f"❌ Error during data processing: {e}")

def train_model_streamlit():
    """Streamlit interface for model training"""
    st.header("🚀 Model Training")

    # Check if processed data exists
    required_files = [
        'processed_data/X_train.csv',
        'processed_data/X_val.csv',
        'processed_data/X_test.csv',
        'processed_data/y_train.csv',
        'processed_data/y_val.csv',
        'processed_data/y_test.csv'
    ]

    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        st.error("❌ Processed data not found!")
        st.info("Please process data first using the 'Process Data' action.")
        return

    st.markdown("Configure and train your ML model.")

    # Collapsible configuration section
    with st.expander("⚙️ Model Configuration", expanded=True):
        # Model configuration
        col1, col2 = st.columns(2)

        with col1:
            model_type = st.selectbox(
                "Model Type",
                ["linear_regression", "random_forest", "neural_network"],
                help="Choose the type of model to train"
            )

        with col2:
            model_name = st.text_input("Model Name", value="wine_quality_model")

        # Model-specific parameters
        if model_type == "random_forest":
            st.subheader("🌳 Random Forest Parameters")
            col1, col2 = st.columns(2)
            with col1:
                n_estimators = st.number_input("Number of Trees", min_value=10, max_value=500, value=100)
            with col2:
                max_depth = st.number_input("Max Depth", min_value=1, max_value=50, value=10)

        elif model_type == "neural_network":
            st.subheader("🧠 Neural Network Parameters")
            col1, col2 = st.columns(2)
            with col1:
                epochs = st.number_input("Epochs", min_value=10, max_value=1000, value=100)
                learning_rate = st.number_input("Learning Rate", min_value=0.0001, max_value=0.1, value=0.001, format="%.4f")
            with col2:
                batch_size = st.number_input("Batch Size", min_value=8, max_value=128, value=32)
                dropout_rate = st.number_input("Dropout Rate", min_value=0.0, max_value=0.5, value=0.2, format="%.2f")

        elif model_type == "linear_regression":
            st.info("ℹ️ Linear regression uses analytical solution - no hyperparameters to configure")

    if st.button("Train Model", type="primary"):
        # Update environment variables temporarily
        os.environ['MODEL_TYPE'] = model_type
        os.environ['MODEL_NAME'] = model_name

        if model_type == "random_forest":
            os.environ['N_ESTIMATORS'] = str(n_estimators)
            os.environ['MAX_DEPTH'] = str(max_depth)
        elif model_type == "neural_network":
            os.environ['EPOCHS'] = str(epochs)
            os.environ['LEARNING_RATE'] = str(learning_rate)
            os.environ['BATCH_SIZE'] = str(batch_size)
            os.environ['DROPOUT_RATE'] = str(dropout_rate)

        try:
            if model_type == "neural_network":
                # Neural network training with live progress
                st.info("🚀 Starting neural network training...")

                # Create progress containers
                progress_bar = st.progress(0)
                epoch_status = st.empty()
                metrics_container = st.empty()
                loss_chart_container = st.empty()

                # Initialize trainer
                trainer = WineQualityTrainer()

                # Train with live updates
                model, metrics = train_neural_network_with_progress(
                    trainer, progress_bar, epoch_status, metrics_container, loss_chart_container
                )

            else:
                # Regular training for sklearn models
                with st.spinner(f"Training {model_type} model..."):
                    trainer = WineQualityTrainer()
                    model, metrics = trainer.train()

            st.success("✅ Training completed!")

            # Show final results
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Model Type", model_type)
            with col2:
                st.metric("Test R²", f"{metrics['test']['r2']:.4f}")
            with col3:
                st.metric("Test RMSE", f"{metrics['test']['rmse']:.4f}")

            st.info("💾 Model saved to 'models/' folder")

        except Exception as e:
            st.error(f"❌ Error during training: {e}")

def test_model_streamlit():
    """Streamlit interface for model testing"""
    st.header("🧪 Model Testing")

    # Load available models
    models_data = load_model_data()

    if not models_data:
        st.error("No trained models found!")
        st.info("Please train a model first using the 'Train Model' action.")
        return

    # Model selection
    selected_model = st.selectbox(
        "Select model to test:",
        list(models_data.keys()),
        format_func=lambda x: f"{x} ({models_data[x]['config']['model_type']})"
    )

    if st.button("Test Model", type="primary"):
        with st.spinner("Testing model..."):
            try:
                # Load test data
                X_test, y_test = load_test_data()

                if X_test is None or y_test is None:
                    st.error("Test data not found! Please process data first.")
                    return

                model_info = models_data[selected_model]
                config = model_info['config']
                model_path = model_info['path']

                # Load and test model
                if config['model_type'] in ['linear_regression', 'random_forest']:
                    model_file = f"{model_path}/model.pkl"
                    with open(model_file, 'rb') as f:
                        model = pickle.load(f)
                    y_pred = model.predict(X_test)
                else:
                    st.error("Neural network testing not yet implemented in UI")
                    return

                # Calculate metrics
                mse = mean_squared_error(y_test, y_pred)
                mae = mean_absolute_error(y_test, y_pred)
                r2 = r2_score(y_test, y_pred)
                rmse = np.sqrt(mse)

                st.success("✅ Testing completed!")

                # Show results
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("R² Score", f"{r2:.4f}")
                with col2:
                    st.metric("RMSE", f"{rmse:.4f}")
                with col3:
                    st.metric("MAE", f"{mae:.4f}")
                with col4:
                    st.metric("MSE", f"{mse:.4f}")

            except Exception as e:
                st.error(f"❌ Error during testing: {e}")

def visualize_models():
    """Streamlit interface for model visualization"""
    st.header("📊 Model Visualization")

    # Load models
    models_data = load_model_data()

    if not models_data:
        st.error("No trained models found!")
        st.info("Please train a model first using the 'Train Model' action.")
        return

    # Model selection
    selected_model = st.selectbox(
        "Choose a model to visualize:",
        list(models_data.keys()),
        format_func=lambda x: f"{x} ({models_data[x]['config']['model_type']})"
    )

    if selected_model:
        model_info = models_data[selected_model]
        config = model_info['config']
        metrics = model_info['metrics']
        model_path = model_info['path']

        # Display model info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**Type:** {config['model_type']}")
        with col2:
            st.info(f"**Test R²:** {metrics.get('test', {}).get('r2', 'N/A'):.4f}")
        with col3:
            st.info(f"**Test RMSE:** {metrics.get('test', {}).get('rmse', 'N/A'):.4f}")

        # Tabs for different visualizations
        tab1, tab2, tab3 = st.tabs(["📈 Training Progress", "🔍 Model Analysis", "📊 Metrics Comparison"])

        with tab1:
            st.subheader("Training History")
            if config['model_type'] == 'neural_network':
                plot_training_history(metrics, selected_model)
            else:
                st.info("Training history is only available for neural network models.")

                # Show final metrics instead
                if 'train' in metrics and 'val' in metrics:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Final Training R²", f"{metrics['train']['r2']:.4f}")
                        st.metric("Final Training RMSE", f"{metrics['train']['rmse']:.4f}")
                    with col2:
                        st.metric("Final Validation R²", f"{metrics['val']['r2']:.4f}")
                        st.metric("Final Validation RMSE", f"{metrics['val']['rmse']:.4f}")

        with tab2:
            st.subheader("Model Analysis")
            X_test, y_test = load_test_data()

            if X_test is not None and y_test is not None:
                if config['model_type'] == 'linear_regression':
                    plot_linear_regression_analysis(model_path, X_test, y_test)
                elif config['model_type'] == 'random_forest':
                    st.info("Random Forest analysis coming soon!")
                elif config['model_type'] == 'neural_network':
                    st.info("Neural Network analysis coming soon!")
            else:
                st.error("Test data not found! Please run data preprocessing first.")

        with tab3:
            st.subheader("Metrics Summary")

            # Create metrics comparison table
            metrics_df = pd.DataFrame({
                'Dataset': ['Training', 'Validation', 'Test'],
                'R²': [
                    metrics.get('train', {}).get('r2', 0),
                    metrics.get('val', {}).get('r2', 0),
                    metrics.get('test', {}).get('r2', 0)
                ],
                'RMSE': [
                    metrics.get('train', {}).get('rmse', 0),
                    metrics.get('val', {}).get('rmse', 0),
                    metrics.get('test', {}).get('rmse', 0)
                ],
                'MAE': [
                    metrics.get('train', {}).get('mae', 0),
                    metrics.get('val', {}).get('mae', 0),
                    metrics.get('test', {}).get('mae', 0)
                ]
            })

            st.dataframe(metrics_df, use_container_width=True)

            # Plot metrics comparison
            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=metrics_df['Dataset'],
                y=metrics_df['R²'],
                name='R²',
                marker_color='blue'
            ))

            fig.update_layout(
                title='Model Performance Across Datasets',
                xaxis_title='Dataset',
                yaxis_title='R² Score',
                template='plotly_white'
            )

            st.plotly_chart(fig, use_container_width=True)

def train_neural_network_with_progress(trainer, progress_bar, epoch_status, metrics_container, loss_chart_container):
    """Train neural network with live Streamlit progress updates"""

    # Load data
    X_train, X_val, X_test, y_train, y_val, y_test = trainer.load_data()

    # Create model
    from src.train_model import ModelFactory
    model_kwargs = {
        'n_estimators': trainer.config['n_estimators'],
        'max_depth': trainer.config['max_depth'],
        'min_samples_split': trainer.config['min_samples_split'],
        'min_samples_leaf': trainer.config['min_samples_leaf'],
        'hidden_layers': trainer.config['hidden_layers'],
        'dropout_rate': trainer.config['dropout_rate'],
        'activation': trainer.config['activation'],
        'random_seed': trainer.config['random_seed'],
        'input_size': X_train.shape[1]
    }

    model = ModelFactory.create_model('neural_network', **model_kwargs)

    # Convert to tensors
    X_train_tensor = torch.FloatTensor(X_train.values)
    y_train_tensor = torch.FloatTensor(y_train.values.reshape(-1, 1))
    X_val_tensor = torch.FloatTensor(X_val.values)
    y_val_tensor = torch.FloatTensor(y_val.values.reshape(-1, 1))

    # Create data loaders
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=trainer.config['batch_size'], shuffle=True)

    # Setup training
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=trainer.config['learning_rate'])

    # Training loop with live updates
    best_val_loss = float('inf')
    patience_counter = 0
    train_losses = []
    val_losses = []
    epochs_completed = 0

    for epoch in range(trainer.config['epochs']):
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

        epochs_completed = epoch + 1

        # Update progress bar
        progress = epochs_completed / trainer.config['epochs']
        progress_bar.progress(progress)

        # Update epoch status
        epoch_status.write(f"**Epoch {epochs_completed}/{trainer.config['epochs']}** - Train Loss: {avg_train_loss:.4f}, Val Loss: {val_loss:.4f}")

        # Update metrics
        with metrics_container.container():
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Current Epoch", epochs_completed)
            with col2:
                st.metric("Train Loss", f"{avg_train_loss:.4f}")
            with col3:
                st.metric("Val Loss", f"{val_loss:.4f}")

        # Update loss chart every 5 epochs or on last epoch
        if epochs_completed % 5 == 0 or epochs_completed == trainer.config['epochs']:
            with loss_chart_container.container():
                fig = go.Figure()
                epochs_range = list(range(1, len(train_losses) + 1))

                fig.add_trace(go.Scatter(
                    x=epochs_range,
                    y=train_losses,
                    mode='lines',
                    name='Training Loss',
                    line=dict(color='blue')
                ))

                fig.add_trace(go.Scatter(
                    x=epochs_range,
                    y=val_losses,
                    mode='lines',
                    name='Validation Loss',
                    line=dict(color='red')
                ))

                fig.update_layout(
                    title='Training Progress (Live)',
                    xaxis_title='Epoch',
                    yaxis_title='Loss',
                    height=400
                )

                st.plotly_chart(fig, use_container_width=True)

        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            best_model_state = model.state_dict().copy()
        else:
            patience_counter += 1
            if patience_counter >= trainer.config['validation_patience']:
                reason = f"Validation loss stopped improving for {trainer.config['validation_patience']} consecutive epochs"
                epoch_status.write(f"🛑 **Early Stopping Triggered:** {reason} (stopped at epoch {epochs_completed})")
                break

        # Small delay to make progress visible
        time.sleep(0.1)

    # Load best model
    model.load_state_dict(best_model_state)

    # Final evaluation
    model.eval()
    with torch.no_grad():
        y_train_pred = model(X_train_tensor).numpy().flatten()
        y_val_pred = model(X_val_tensor).numpy().flatten()

    train_metrics = trainer.evaluate_model(y_train, y_train_pred, "Training")
    val_metrics = trainer.evaluate_model(y_val, y_val_pred, "Validation")

    # Test evaluation
    with torch.no_grad():
        X_test_tensor = torch.FloatTensor(X_test.values)
        y_test_pred = model(X_test_tensor).numpy().flatten()

    test_metrics = trainer.evaluate_model(y_test, y_test_pred, "Test")

    # Prepare metrics for saving
    metrics = {
        'train': train_metrics,
        'val': val_metrics,
        'test': test_metrics,
        'train_losses': train_losses,
        'val_losses': val_losses
    }

    # Save model and results
    trainer.save_model_and_results(model, metrics, trainer.config['model_name'])

    return model, metrics

def main():
    st.title("🍷 Wine Quality ML Pipeline")
    st.markdown("Complete machine learning pipeline for wine quality prediction")

    # Sidebar for action selection
    st.sidebar.title("🎯 Actions")
    st.sidebar.markdown("Choose an action:")

    # Initialize session state for action tracking
    if 'current_action' not in st.session_state:
        st.session_state.current_action = "🔄 Process Data"

    # Action buttons
    if st.sidebar.button("🔄 Process Data", type="primary" if st.session_state.current_action == "🔄 Process Data" else "secondary"):
        st.session_state.current_action = "🔄 Process Data"

    if st.sidebar.button("🚀 Train Model", type="primary" if st.session_state.current_action == "🚀 Train Model" else "secondary"):
        st.session_state.current_action = "🚀 Train Model"

    if st.sidebar.button("🧪 Test Model", type="primary" if st.session_state.current_action == "🧪 Test Model" else "secondary"):
        st.session_state.current_action = "🧪 Test Model"

    if st.sidebar.button("📊 Visualize Models", type="primary" if st.session_state.current_action == "📊 Visualize Models" else "secondary"):
        st.session_state.current_action = "📊 Visualize Models"

    # Main content based on selected action
    if st.session_state.current_action == "🔄 Process Data":
        process_data_streamlit()
    elif st.session_state.current_action == "🚀 Train Model":
        train_model_streamlit()
    elif st.session_state.current_action == "🧪 Test Model":
        test_model_streamlit()
    elif st.session_state.current_action == "📊 Visualize Models":
        visualize_models()

if __name__ == "__main__":
    main()