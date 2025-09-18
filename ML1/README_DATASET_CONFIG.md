# Generalized Dataset Configuration

This ML pipeline now supports multiple datasets through configuration files. Here's how to use different datasets:

## Configuration Structure

Create JSON configuration files in the `configs/` directory with the following structure:

```json
{
  "name": "Dataset Display Name",
  "loader_type": "csv|wine_quality",
  "files": [
    {
      "path": "path/to/data.csv",
      "add_columns": {
        "column_name": "value"
      }
    }
  ],
  "target_column": "target_column_name",
  "separator": ",",
  "test_size": 0.2,
  "val_size": 0.5,
  "random_state": 42,
  "scale_features": true,
  "exclude_columns": ["col1", "col2"],
  "include_columns": ["col1", "col2"],
  "feature_engineering": {}
}
```

## Configuration Options

- **name**: Human-readable dataset name
- **loader_type**: Type of loader (`csv` for generic CSV, `wine_quality` for wine datasets)
- **files**: Array of file configurations
  - **path**: Path to the CSV file
  - **add_columns**: Additional columns to add (useful for combining datasets)
- **target_column**: Name of the target variable column
- **separator**: CSV separator (`,`, `;`, etc.)
- **test_size**: Proportion of data for testing (0.0-1.0)
- **val_size**: Proportion of temp data for validation (0.0-1.0)
- **random_state**: Random seed for reproducibility
- **scale_features**: Whether to standardize features
- **exclude_columns**: Columns to remove from features
- **include_columns**: If specified, only include these columns (plus target)
- **feature_engineering**: Custom transformations (advanced)

## Using Different Datasets

### Environment Variables

Set the `DATASET_CONFIG` environment variable to use a specific configuration:

```bash
# Use Boston housing dataset
export DATASET_CONFIG=configs/boston_housing.json
python -m src.train_model

# Use Iris dataset
export DATASET_CONFIG=configs/iris.json
python -m src.train_model
```

### In Code

```python
from src.preprocess_data import load_and_preprocess_data

# Load specific dataset
X_train, X_val, X_test, y_train, y_val, y_test, scaler = load_and_preprocess_data('configs/iris.json')

# Or use dictionary configuration
config = {
    "name": "My Dataset",
    "files": [{"path": "data/my_data.csv"}],
    "target_column": "target",
    "separator": ","
}
X_train, X_val, X_test, y_train, y_val, y_test, scaler = load_and_preprocess_data(config)
```

## Available Configurations

1. **wine_quality.json**: Wine quality dataset (default)
2. **iris.json**: Iris classification dataset
3. **boston_housing.json**: Boston housing price prediction

## Adding New Datasets

1. Place your CSV file(s) in the `data/` directory
2. Create a configuration file in `configs/`
3. Set the appropriate parameters for your dataset
4. Use the configuration in your training pipeline

## Backwards Compatibility

The original `load_and_preprocess_wine_data()` function still works and defaults to the wine quality configuration.