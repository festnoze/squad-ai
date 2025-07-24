# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Turtle is a Python + Streamlit application for displaying interactive candlestick charts from JSON data files. It's a financial data visualization tool that loads trading data and renders it as interactive charts.

## Development Commands

### Setup and Environment
```bash
# Create virtual environment
create_venv.bat

# Activate environment (must be done manually)
venv\Scripts\activate.bat

# Install dependencies with uv (requires activated venv)
install_requirements.bat

# Run the application (auto-activates venv)
run_app.bat
```

### Running the Application
The app runs via Streamlit from the `src/` directory:
```bash
cd src
streamlit run app.py
```

## Architecture

### Core Components
- **`src/app.py`**: Main Streamlit application with UI logic and chart rendering
- **`src/models.py`**: Data models using dataclasses for type safety
- **`data/`**: Directory containing JSON chart files

### Data Flow
```
JSON Files → ChartData.from_json_file() → DataFrame → Plotly Chart → Streamlit UI
```

### Key Models
- `Candle`: OHLC data with timestamp
- `ChartMetadata`: Asset name, currency, period duration  
- `ChartData`: Container combining metadata with candle list

## Data Format

Chart files are JSON with this structure:
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

## Technology Stack

- **Streamlit**: Web application framework
- **Plotly**: Interactive charting (candlestick charts)
- **Pandas**: Data manipulation
- **uv**: Fast Python package installer (preferred over pip)

## Development Notes

### Package Management
This project uses `uv` instead of pip for faster dependency installation. The `install_requirements.bat` script handles this automatically.

### File Organization
- UI logic and chart rendering in `app.py`
- Data models and JSON parsing in `models.py`
- Clean separation between data layer and presentation layer

### Error Handling
The app gracefully handles missing data directory and malformed JSON files with user-friendly Streamlit error messages.

### Chart Configuration
- Candlestick charts use full container width
- Range slider is disabled for cleaner appearance
- Charts show asset name, currency, and period in title