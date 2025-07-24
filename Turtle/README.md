# Chart Viewer

A Python + Streamlit application for loading and displaying candlestick charts from JSON files.

## Features

- Load chart data from JSON files
- Display interactive candlestick charts
- Support for multiple assets and currencies
- Configurable time periods

## Setup

1. **Create virtual environment:**
   ```bash
   create_venv.bat
   ```

2. **Activate virtual environment:**
   ```bash
   venv\Scripts\activate.bat
   ```

3. **Install requirements with uv:**
   ```bash
   install_requirements.bat
   ```

4. **Run the application:**
   ```bash
   run_app.bat
   ```

## Chart Data Format

Place JSON files in the `data/` directory with the following structure:

```json
{
  "metadata": {
    "asset_name": "Bitcoin",
    "currency": "USD",
    "period_duration": "1min"
  },
  "candles": [
    {
      "timestamp": "2024-01-01T10:00:00",
      "open": 42000.50,
      "close": 42100.25,
      "high": 42150.75,
      "low": 41950.30
    }
  ]
}
```

## Project Structure

```
chart-viewer/
├── src/
│   ├── app.py          # Main Streamlit application
│   └── models.py       # Data models
├── data/               # Chart data files (JSON)
├── requirements.txt    # Python dependencies
├── create_venv.bat     # Create virtual environment
├── install_requirements.bat  # Install dependencies with uv
└── run_app.bat         # Run the application
```