import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import random
import os
import yfinance as yf
import pandas as pd
import requests

def validate_date_range(start_date, end_date):
    """Validate date range parameters
    
    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not start_date or not end_date:
        return True, None
        
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        if start_dt >= end_dt:
            return False, "Start date must be before end date"
            
        if end_dt > datetime.now():
            return False, "End date cannot be in the future"
            
        # Check if date range is reasonable (not more than 5 years)
        if (end_dt - start_dt).days > 5 * 365:
            return False, "Date range cannot exceed 5 years"
            
        return True, None
        
    except ValueError as e:
        return False, f"Invalid date format. Use YYYY-MM-DD format. Error: {e}"

def download_eur_usd_data(base_currency="EUR", quote_currency="USD", limit=100, asset_name="Euro", interval="1d", start_date=None, end_date=None):
    """Download real historical forex data from Alpha Vantage API with intelligent chunking
    
    Args:
        base_currency: Base currency (e.g., EUR, GBP, JPY)
        quote_currency: Quote currency (e.g., USD, EUR)
        limit: Number of recent candles to download (if no date range specified)
        asset_name: Display name for the asset
        interval: Time interval (daily only for free tier)
        start_date: Start date for historical data (YYYY-MM-DD format)
        end_date: End date for historical data (YYYY-MM-DD format)
    """
    # Validate date range if provided
    if start_date and end_date:
        is_valid, error_msg = validate_date_range(start_date, end_date)
        if not is_valid:
            print(f"Date validation error: {error_msg}")
            return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
    
    # Alpha Vantage free API key (demo key, replace with your own)
    api_key = "demo"  # Replace with actual API key for production use
    
    # Use Alpha Vantage FX_DAILY function for historical forex data
    symbol_pair = f"{base_currency}{quote_currency}"
    url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={base_currency}&to_symbol={quote_currency}&apikey={api_key}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
        
        # Check for API errors
        if "Error Message" in data:
            print(f"Alpha Vantage API Error: {data['Error Message']}")
            return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
        
        if "Note" in data:
            print(f"Alpha Vantage API Limit: {data['Note']}")
            return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
        
        if "Time Series FX (Daily)" not in data:
            print("No forex data available from Alpha Vantage")
            return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
        
        time_series = data["Time Series FX (Daily)"]
        candles = []
        
        # Filter data by date range if specified
        for date_str, daily_data in time_series.items():
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Apply date filter if specified
            if start_date and end_date:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                if not (start_date_obj <= date_obj <= end_date_obj):
                    continue
            
            candles.append({
                "timestamp": f"{date_str}T00:00:00",
                "open": float(daily_data["1. open"]),
                "high": float(daily_data["2. high"]),
                "low": float(daily_data["3. low"]),
                "close": float(daily_data["4. close"])
            })
            
            # Limit results if no date range specified
            if not (start_date and end_date) and len(candles) >= limit:
                break
        
        # Sort candles by timestamp (oldest first)
        candles.sort(key=lambda x: x["timestamp"])
        
        chart_data = {
            "metadata": {
                "asset_name": asset_name,
                "currency": quote_currency,
                "period_duration": interval
            },
            "candles": candles
        }
        
        _save_forex_chart_data(chart_data, base_currency, quote_currency, interval, "alphavantage")
        print(f"Downloaded {len(candles)} {base_currency}/{quote_currency} historical daily candles from Alpha Vantage")
        return True
        
    except Exception as e:
        print(f"Error downloading {base_currency}/{quote_currency} data from Alpha Vantage: {e}")
        return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)

def _save_forex_chart_data(chart_data, base_currency, quote_currency, interval, source="unknown"):
    """Save forex chart data to file with source identifier"""
    if chart_data['candles']:
        start_dt = datetime.fromisoformat(chart_data['candles'][0]['timestamp'])
        end_dt = datetime.fromisoformat(chart_data['candles'][-1]['timestamp'])
        start_date_str = start_dt.strftime("%Y-%m-%d")
        start_time_str = start_dt.strftime("%H-%M-%S")
        end_date_str = end_dt.strftime("%Y-%m-%d")
        end_time_str = end_dt.strftime("%H-%M-%S")
        filename = f"../inputs/{base_currency.lower()}{quote_currency.lower()}_{interval}_{source}_{start_date_str}_{start_time_str}_{end_date_str}_{end_time_str}.json"
    else:
        filename = f"../inputs/{base_currency.lower()}{quote_currency.lower()}_{interval}_{source}_nodata.json"
        
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w') as f:
        json.dump(chart_data, f, indent=2)

def _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date=None, end_date=None):
    """Fallback to synthetic forex data when Alpha Vantage is not available"""
    print(f"Falling back to synthetic data for {base_currency}/{quote_currency}")
    
    # Using exchangerate-api.com as fallback
    url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
        
        if quote_currency not in data['rates']:
            print(f"Currency pair {base_currency}/{quote_currency} not available")
            return False
        
        base_rate = data['rates'][quote_currency]
        candles = []
        
        # Generate date range or recent data
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            current_dt = start_dt
            
            while current_dt <= end_dt:
                variation = random.uniform(-0.01, 0.01)
                open_price = base_rate + variation
                close_price = base_rate + random.uniform(-0.01, 0.01)
                high_price = max(open_price, close_price) + abs(random.uniform(0, 0.005))
                low_price = min(open_price, close_price) - abs(random.uniform(0, 0.005))
                
                candles.append({
                    "timestamp": current_dt.strftime("%Y-%m-%dT00:00:00"),
                    "open": round(open_price, 5),
                    "high": round(high_price, 5),
                    "low": round(low_price, 5),
                    "close": round(close_price, 5)
                })
                current_dt += timedelta(days=1)
        else:
            # Generate recent synthetic data
            for i in range(limit):
                timestamp = datetime.now() - timedelta(days=limit-i)
                variation = random.uniform(-0.01, 0.01)
                open_price = base_rate + variation
                close_price = base_rate + random.uniform(-0.01, 0.01)
                high_price = max(open_price, close_price) + abs(random.uniform(0, 0.005))
                low_price = min(open_price, close_price) - abs(random.uniform(0, 0.005))
                
                candles.append({
                    "timestamp": timestamp.strftime("%Y-%m-%dT00:00:00"),
                    "open": round(open_price, 5),
                    "high": round(high_price, 5),
                    "low": round(low_price, 5),
                    "close": round(close_price, 5)
                })
        
        chart_data = {
            "metadata": {
                "asset_name": asset_name,
                "currency": quote_currency,
                "period_duration": interval
            },
            "candles": candles
        }
        
        # Save the data using the centralized function
        _save_forex_chart_data(chart_data, base_currency, quote_currency, interval, "synthetic")
        
        print(f"Generated {len(candles)} {base_currency}/{quote_currency} synthetic daily candles")
        return True
        
    except Exception as e:
        print(f"Error generating fallback {base_currency}/{quote_currency} data: {e}")
        return False

def yfinance_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date=None, end_date=None):
    """Get forex data using yfinance as an alternative to the fallback method
    
    Args:
        base_currency: Base currency (e.g., EUR, GBP, JPY)
        quote_currency: Quote currency (e.g., USD, EUR)
        limit: Number of recent candles to download (if no date range specified)
        asset_name: Display name for the asset
        interval: Time interval (1d for daily, 1wk for weekly, 1mo for monthly)
        start_date: Start date for historical data (YYYY-MM-DD format)
        end_date: End date for historical data (YYYY-MM-DD format)
        
    Returns:
        bool: True if successful, False otherwise
    """
    print(f"Fetching {base_currency}/{quote_currency} data using yfinance")
    
    try:
        # Create yfinance ticker symbol for forex pair
        # yfinance uses format like "EURUSD=X" for forex pairs
        yf_symbol = f"{base_currency}{quote_currency}=X"
        ticker = yf.Ticker(yf_symbol)
        
        # Map interval to yfinance format
        yf_interval_map = {
            "1d": "1d",
            "1w": "1wk", 
            "1mo": "1mo"
        }
        yf_interval = yf_interval_map.get(interval, "1d")
        
        # Determine date range for data fetch
        if start_date and end_date:
            # Use provided date range
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # Include end date
        else:
            # Use limit to determine how far back to go
            end_dt = datetime.now()
            if interval == "1w":
                start_dt = end_dt - timedelta(weeks=limit)
            elif interval == "1mo":
                start_dt = end_dt - timedelta(days=limit * 30)
            else:  # daily
                start_dt = end_dt - timedelta(days=limit)
        
        # Fetch historical data
        hist_data = ticker.history(
            start=start_dt,
            end=end_dt,
            interval=yf_interval,
            auto_adjust=True,
            prepost=False
        )
        
        if hist_data.empty:
            print(f"No data available for {yf_symbol} from yfinance")
            return False
        
        # Convert to our candle format
        candles = []
        for timestamp, row in hist_data.iterrows():
            # Handle timezone-aware timestamps
            if hasattr(timestamp, 'tz_localize'):
                # If timezone-naive, assume UTC
                if timestamp.tz is None:
                    timestamp = timestamp.tz_localize('UTC')
                # Convert to local timezone for consistency
                timestamp = timestamp.tz_convert(None)
            
            candles.append({
                "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                "open": round(float(row['Open']), 5),
                "high": round(float(row['High']), 5), 
                "low": round(float(row['Low']), 5),
                "close": round(float(row['Close']), 5)
            })
        
        # Sort candles by timestamp (should already be sorted)
        candles.sort(key=lambda x: x["timestamp"])
        
        # Apply limit if no date range was specified
        if not (start_date and end_date) and len(candles) > limit:
            candles = candles[-limit:]  # Take most recent candles
        
        chart_data = {
            "metadata": {
                "asset_name": asset_name,
                "currency": quote_currency,
                "period_duration": interval
            },
            "candles": candles
        }
        
        # Save the data
        _save_forex_chart_data(chart_data, base_currency, quote_currency, interval, "yfinance")
        print(f"Downloaded {len(candles)} {base_currency}/{quote_currency} candles from yfinance")
        return True
        
    except Exception as e:
        print(f"Error downloading {base_currency}/{quote_currency} data from yfinance: {e}")
        return False


class CandleFetcher:
    """Enhanced candle data fetcher with Binance API support for forex pairs"""
    
    def _to_milliseconds(self, dt_str: str) -> int:
        """Convert datetime string to milliseconds timestamp"""
        dt: datetime = datetime.fromisoformat(dt_str)
        return int(dt.timestamp() * 1000)

    def fetch_binance_klines(self, symbol: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch klines data from Binance API with pagination support
        
        Args:
            symbol: Trading pair symbol (e.g., EURUSD, GBPUSD)
            interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
            start_date: Start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            end_date: End date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            
        Returns:
            DataFrame with OHLCV data
        """
        start_ms: int = self._to_milliseconds(start_date)
        end_ms: int = self._to_milliseconds(end_date)
        url: str = "https://api.binance.com/api/v3/klines"
        all_data: list = []
        
        while start_ms < end_ms:
            params: dict = {
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data: list = response.json()
                
                if not data:
                    break
                    
                all_data.extend(data)
                last_open_time: int = data[-1][0]
                
                if len(data) < 1000:
                    break
                    
                start_ms = last_open_time + 1
                
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                break
        
        columns: list = [
            "open_time",
            "open",
            "high", 
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "num_trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ]
        
        df = pd.DataFrame(all_data, columns=columns)
        
        if not df.empty:
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df[["open", "high", "low", "close", "volume"]] = df[
                ["open", "high", "low", "close", "volume"]
            ].astype(float)
        
        return df

    def binance_forex_data(self, symbol: str, interval: str, start_date: str, end_date: str, 
                          asset_name: str, quote_currency: str) -> bool:
        """Download forex data using Binance API and save to our standard format
        
        Args:
            symbol: Forex symbol (e.g., EURUSD)
            interval: Time interval
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD) 
            asset_name: Display name for the asset
            quote_currency: Quote currency
            
        Returns:
            bool: True if successful, False otherwise
        """
        print(f"Fetching {symbol} forex data from Binance API")
        
        try:
            # Validate date range
            is_valid, error_msg = validate_date_range(start_date, end_date)
            if not is_valid:
                print(f"Date validation error: {error_msg}")
                return False
            
            # Convert dates to ISO format for the API
            start_iso = f"{start_date}T00:00:00"
            end_iso = f"{end_date}T23:59:59"
            
            # Fetch data using the enhanced method
            df = self.fetch_binance_klines(symbol, interval, start_iso, end_iso)
            
            if df.empty:
                print(f"No data available for {symbol}")
                return False
            
            # Convert to our standard candle format
            candles = []
            for _, row in df.iterrows():
                candles.append({
                    "timestamp": row["open_time"].isoformat(),
                    "open": round(float(row["open"]), 5),
                    "high": round(float(row["high"]), 5),
                    "low": round(float(row["low"]), 5), 
                    "close": round(float(row["close"]), 5)
                })
            
            # Sort candles by timestamp
            candles.sort(key=lambda x: x["timestamp"])
            
            chart_data = {
                "metadata": {
                    "asset_name": asset_name,
                    "currency": quote_currency,
                    "period_duration": interval
                },
                "candles": candles
            }
            
            # Save the data
            base_currency = symbol[:3]
            _save_forex_chart_data(chart_data, base_currency, quote_currency, interval)
            print(f"Downloaded {len(candles)} {symbol} candles from Binance API")
            return True
            
        except Exception as e:
            print(f"Error downloading {symbol} data from Binance: {e}")
            return False

    def fetch_and_convert(self, symbol: str, interval: str, start_date: str, end_date: str,
                         asset_name: str, quote_currency: str) -> dict:
        """Fetch data and return in our standard chart format
        
        Args:
            symbol: Trading pair symbol
            interval: Time interval  
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            asset_name: Display name for the asset
            quote_currency: Quote currency
            
        Returns:
            dict: Chart data in standard format or None if failed
        """
        start_iso = f"{start_date}T00:00:00"
        end_iso = f"{end_date}T23:59:59"
        
        df = self.fetch_binance_klines(symbol, interval, start_iso, end_iso)
        
        if df.empty:
            return None
        
        candles = []
        for _, row in df.iterrows():
            candles.append({
                "timestamp": row["open_time"].isoformat(),
                "open": round(float(row["open"]), 5),
                "high": round(float(row["high"]), 5),
                "low": round(float(row["low"]), 5),
                "close": round(float(row["close"]), 5)
            })
        
        return {
            "metadata": {
                "asset_name": asset_name,
                "currency": quote_currency,
                "period_duration": interval
            },
            "candles": sorted(candles, key=lambda x: x["timestamp"])
        }


def _to_milliseconds(dt_str: str) -> int:
    """Convert datetime string to milliseconds timestamp"""
    dt: datetime = datetime.fromisoformat(dt_str)
    return int(dt.timestamp() * 1000)

def _fetch_binance_klines(symbol: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch klines data from Binance API with pagination support
    
    Args:
        symbol: Trading pair symbol (e.g., EURUSD, GBPUSD)
        interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
        start_date: Start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        end_date: End date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        
    Returns:
        DataFrame with OHLCV data
    """
    start_ms: int = _to_milliseconds(start_date)
    end_ms: int = _to_milliseconds(end_date)
    url: str = "https://api.binance.com/api/v3/klines"
    all_data: list = []
    
    while start_ms < end_ms:
        params: dict = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data: list = response.json()
            
            if not data:
                break
                
            all_data.extend(data)
            last_open_time: int = data[-1][0]
            
            if len(data) < 1000:
                break
                
            start_ms = last_open_time + 1
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            break
    
    columns: list = [
        "open_time",
        "open",
        "high", 
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "num_trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]
    
    df = pd.DataFrame(all_data, columns=columns)
    
    if not df.empty:
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df[["open", "high", "low", "close", "volume"]] = df[
            ["open", "high", "low", "close", "volume"]
        ].astype(float)
    
    return df

def download_binance_forex_data(symbol="EURUSD", interval="1h", asset_name="Euro", quote_currency="USD", 
                               start_date=None, end_date=None):
    """Download forex data from Binance API with enhanced pagination support
    
    Args:
        symbol: Forex symbol (e.g., EURUSD, GBPUSD)
        interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
        asset_name: Display name for the asset
        quote_currency: Quote currency
        start_date: Start date for historical data (YYYY-MM-DD format)
        end_date: End date for historical data (YYYY-MM-DD format)
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not (start_date and end_date):
        print("Start date and end date are required for Binance forex data")
        return False
    
    print(f"Fetching {symbol} forex data from Binance API")
    
    try:
        # Validate date range
        is_valid, error_msg = validate_date_range(start_date, end_date)
        if not is_valid:
            print(f"Date validation error: {error_msg}")
            return False
        
        # Convert dates to ISO format for the API
        start_iso = f"{start_date}T00:00:00"
        end_iso = f"{end_date}T23:59:59"
        
        # Fetch data using the enhanced method
        df = _fetch_binance_klines(symbol, interval, start_iso, end_iso)
        
        if df.empty:
            print(f"No data available for {symbol}")
            return False
        
        # Convert to our standard candle format
        candles = []
        for _, row in df.iterrows():
            candles.append({
                "timestamp": row["open_time"].isoformat(),
                "open": round(float(row["open"]), 5),
                "high": round(float(row["high"]), 5),
                "low": round(float(row["low"]), 5), 
                "close": round(float(row["close"]), 5)
            })
        
        # Sort candles by timestamp
        candles.sort(key=lambda x: x["timestamp"])
        
        chart_data = {
            "metadata": {
                "asset_name": asset_name,
                "currency": quote_currency,
                "period_duration": interval
            },
            "candles": candles
        }
        
        # Save the data
        base_currency = symbol[:3]
        _save_forex_chart_data(chart_data, base_currency, quote_currency, interval, "binance")
        print(f"Downloaded {len(candles)} {symbol} candles from Binance API")
        return True
        
    except Exception as e:
        print(f"Error downloading {symbol} data from Binance: {e}")
        return False


def download_forex_data(base_currency="EUR", quote_currency="USD", limit=100, asset_name="Euro", 
                       interval="1d", start_date=None, end_date=None, source="alpha_vantage"):
    """Download forex data from various sources with source selection
    
    Args:
        base_currency: Base currency (e.g., EUR, GBP, JPY)
        quote_currency: Quote currency (e.g., USD, EUR)
        limit: Number of recent candles to download (if no date range specified)
        asset_name: Display name for the asset
        interval: Time interval
        start_date: Start date for historical data (YYYY-MM-DD format)
        end_date: End date for historical data (YYYY-MM-DD format)
        source: Data source ("alpha_vantage", "yfinance", "binance", "synthetic")
        
    Returns:
        bool: True if successful, False otherwise
    """
    symbol = f"{base_currency}{quote_currency}"
    
    print(f"Downloading {base_currency}/{quote_currency} data from {source}")
    
    if source == "alpha_vantage":
        # Use Alpha Vantage (existing download_eur_usd_data function)
        return download_eur_usd_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
    
    elif source == "yfinance":
        # Use yfinance
        return yfinance_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
    
    elif source == "binance":
        # Use Binance API (requires start_date and end_date)
        if not (start_date and end_date):
            print("Binance source requires both start_date and end_date")
            return False
        return download_binance_forex_data(symbol, interval, asset_name, quote_currency, start_date, end_date)
    
    elif source == "synthetic":
        # Use synthetic/fallback data
        return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)
    
    else:
        print(f"Unknown forex data source: {source}")
        print("Available sources: alpha_vantage, yfinance, binance, synthetic")
        return False