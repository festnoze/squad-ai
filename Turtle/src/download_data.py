import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import time
import random
import os
import re

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


def calculate_expected_candles(start_date, end_date, interval):
    """Calculate expected number of candles for a date range and interval
    
    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
        
    Returns:
        int: Expected number of candles
    """
    if not start_date or not end_date:
        return 0
        
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days + 1
    
    # Interval to minutes mapping
    interval_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "12h": 720,
        "1d": 1440,
        "1w": 10080
    }
    
    minutes_per_interval = interval_minutes.get(interval, 1)
    minutes_per_day = 24 * 60
    candles_per_day = minutes_per_day // minutes_per_interval
    
    # For weekly intervals, calculate differently
    if interval == "1w":
        return total_days // 7
    
    return total_days * candles_per_day


def chunk_date_range_by_candles(start_date, end_date, interval, max_candles=950):
    """Split date range into chunks based on expected candle count
    
    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        interval: Time interval
        max_candles: Maximum candles per chunk
        
    Returns:
        list: List of (start_date, end_date) tuples
    """
    if not start_date or not end_date:
        return [(start_date, end_date)]
        
    total_expected = calculate_expected_candles(start_date, end_date, interval)
    
    if total_expected <= max_candles:
        return [(start_date, end_date)]
    
    # Calculate days per chunk based on candle limit
    interval_minutes = {
        "1m": 1, "5m": 5, "15m": 15, "1h": 60,
        "4h": 240, "12h": 720, "1d": 1440, "1w": 10080
    }
    
    minutes_per_interval = interval_minutes.get(interval, 1)
    minutes_per_day = 24 * 60
    candles_per_day = minutes_per_day // minutes_per_interval
    
    if interval == "1w":
        days_per_chunk = max_candles * 7  # 950 weeks = ~13 years
    else:
        days_per_chunk = max_candles // candles_per_day
        if days_per_chunk < 1:
            days_per_chunk = 1
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    chunks = []
    current_start = start_dt
    
    while current_start <= end_dt:
        current_end = min(current_start + timedelta(days=days_per_chunk - 1), end_dt)
        chunks.append((
            current_start.strftime("%Y-%m-%d"),
            current_end.strftime("%Y-%m-%d")
        ))
        current_start = current_end + timedelta(days=1)
        
    return chunks

def combine_chart_data(chart_data_list):
    """Combine multiple chart data objects into one
    
    Args:
        chart_data_list: List of chart data dictionaries
        
    Returns:
        dict: Combined chart data
    """
    if not chart_data_list:
        return None
    
    if len(chart_data_list) == 1:
        return chart_data_list[0]
    
    # Use metadata from first dataset
    combined_data = {
        "metadata": chart_data_list[0]["metadata"],
        "candles": []
    }
    
    # Collect all candles and sort by timestamp
    all_candles = []
    for chart_data in chart_data_list:
        all_candles.extend(chart_data["candles"])
    
    # Sort by timestamp and remove duplicates
    all_candles.sort(key=lambda x: x["timestamp"])
    
    # Remove duplicate timestamps (keep first occurrence)
    seen_timestamps = set()
    for candle in all_candles:
        if candle["timestamp"] not in seen_timestamps:
            combined_data["candles"].append(candle)
            seen_timestamps.add(candle["timestamp"])
    
    return combined_data

def download_crypto_data_chunk(symbol, interval, start_date, end_date, asset_name, currency):
    """Download cryptocurrency data for a single date range chunk
    
    Args:
        symbol: Trading pair symbol
        interval: Time interval
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        asset_name: Display name for the asset
        currency: Quote currency
        
    Returns:
        dict: Chart data or None if failed
    """
    url = "https://api.binance.com/api/v3/klines"
    
    # Convert dates to timestamps (milliseconds)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
    
    params = {
        'symbol': symbol,
        'interval': interval,
        'startTime': int(start_dt.timestamp() * 1000),
        'endTime': int(end_dt.timestamp() * 1000),
        'limit': 1000
    }
    
    params_encoded = urllib.parse.urlencode(params)
    full_url = f"{url}?{params_encoded}"
    
    try:
        with urllib.request.urlopen(full_url) as response:
            data = json.loads(response.read().decode())
        
        candles = []
        for item in data:
            candles.append({
                "timestamp": datetime.fromtimestamp(item[0] / 1000).isoformat(),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4])
            })
        
        return {
            "metadata": {
                "asset_name": asset_name,
                "currency": currency,
                "period_duration": interval
            },
            "candles": candles
        }
        
    except Exception as e:
        print(f"Error downloading {symbol} chunk {start_date} to {end_date}: {e}")
        return None


def download_crypto_data(symbol="BTCUSDT", interval="1m", limit=1000, asset_name="Bitcoin", currency="USDT", start_date=None, end_date=None):
    """Download cryptocurrency data from Binance API with intelligent chunking
    
    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT, ETHUSDT)
        interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
        limit: Number of candles to download (used if no date range specified)
        asset_name: Display name for the asset
        currency: Quote currency
        start_date: Start date for historical data (YYYY-MM-DD format)
        end_date: End date for historical data (YYYY-MM-DD format)
    """
    # Handle single requests without date range
    if not (start_date and end_date):
        url = "https://api.binance.com/api/v3/klines"
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        params_encoded = urllib.parse.urlencode(params)
        full_url = f"{url}?{params_encoded}"
        
        try:
            with urllib.request.urlopen(full_url) as response:
                data = json.loads(response.read().decode())
            
            candles = []
            for item in data:
                candles.append({
                    "timestamp": datetime.fromtimestamp(item[0] / 1000).isoformat(),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4])
                })
            
            chart_data = {
                "metadata": {
                    "asset_name": asset_name,
                    "currency": currency,
                    "period_duration": interval
                },
                "candles": candles
            }
            
            # Generate filename
            if candles:
                start_dt = datetime.fromtimestamp(data[0][0] / 1000)
                end_dt = datetime.fromtimestamp(data[-1][0] / 1000)
                start_date_str = start_dt.strftime("%Y-%m-%d")
                start_time = start_dt.strftime("%H-%M-%S")
                end_date_str = end_dt.strftime("%Y-%m-%d")
                end_time = end_dt.strftime("%H-%M-%S")
                filename = f"../inputs/{symbol.lower()}_{interval}_{start_date_str}_{start_time}_{end_date_str}_{end_time}.json"
            else:
                filename = f"../inputs/{symbol.lower()}_{interval}_nodata.json"
                
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            with open(filename, 'w') as f:
                json.dump(chart_data, f, indent=2)
            
            print(f"Downloaded {len(candles)} {symbol} {interval} candles")
            return True
            
        except Exception as e:
            print(f"Error downloading {symbol} data: {e}")
            return False
    
    # Validate date range
    is_valid, error_msg = validate_date_range(start_date, end_date)
    if not is_valid:
        print(f"Date validation error: {error_msg}")
        return False
    
    # Check if we need to chunk based on expected candle count
    expected_candles = calculate_expected_candles(start_date, end_date, interval)
    
    if expected_candles > 1000:
        print(f"Expected {expected_candles} candles, splitting into chunks of 950...")
        return _download_crypto_data_chunked(symbol, interval, start_date, end_date, asset_name, currency)
    
    # Try single download
    chart_data = download_crypto_data_chunk(symbol, interval, start_date, end_date, asset_name, currency)
    if chart_data:
        _save_chart_data(chart_data, symbol, interval)
        print(f"Downloaded {len(chart_data['candles'])} {symbol} {interval} candles")
        return True
    
    return False


def _download_crypto_data_chunked(symbol, interval, start_date, end_date, asset_name, currency):
    """Download cryptocurrency data in chunks of 950 candles"""
    chunks = chunk_date_range_by_candles(start_date, end_date, interval, 950)
    chart_data_list = []
    
    print(f"Downloading {len(chunks)} chunks...")
    
    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        expected = calculate_expected_candles(chunk_start, chunk_end, interval)
        print(f"Downloading chunk {i}/{len(chunks)}: {chunk_start} to {chunk_end} (~{expected} candles)")
        
        chunk_data = download_crypto_data_chunk(symbol, interval, chunk_start, chunk_end, asset_name, currency)
        if chunk_data:
            chart_data_list.append(chunk_data)
            time.sleep(0.1)  # Rate limiting
        else:
            print(f"Failed to download chunk {i}")
    
    if chart_data_list:
        combined_data = combine_chart_data(chart_data_list)
        _save_chart_data(combined_data, symbol, interval)
        print(f"Successfully downloaded {len(combined_data['candles'])} {symbol} {interval} candles from {len(chunks)} chunks")
        return True
    
    return False


def _save_chart_data(chart_data, symbol, interval):
    """Save chart data to file"""
    if chart_data['candles']:
        start_dt = datetime.fromisoformat(chart_data['candles'][0]['timestamp'])
        end_dt = datetime.fromisoformat(chart_data['candles'][-1]['timestamp'])
        start_date_str = start_dt.strftime("%Y-%m-%d")
        start_time = start_dt.strftime("%H-%M-%S")
        end_date_str = end_dt.strftime("%Y-%m-%d")
        end_time = end_dt.strftime("%H-%M-%S")
        filename = f"../inputs/{symbol.lower()}_{interval}_{start_date_str}_{start_time}_{end_date_str}_{end_time}.json"
    else:
        filename = f"../inputs/{symbol.lower()}_{interval}_nodata.json"
        
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w') as f:
        json.dump(chart_data, f, indent=2)

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
        
        _save_forex_chart_data(chart_data, base_currency, quote_currency, interval)
        print(f"Downloaded {len(candles)} {base_currency}/{quote_currency} historical daily candles from Alpha Vantage")
        return True
        
    except Exception as e:
        print(f"Error downloading {base_currency}/{quote_currency} data from Alpha Vantage: {e}")
        return _fallback_forex_data(base_currency, quote_currency, limit, asset_name, interval, start_date, end_date)




def _save_forex_chart_data(chart_data, base_currency, quote_currency, interval):
    """Save forex chart data to file"""
    if chart_data['candles']:
        start_dt = datetime.fromisoformat(chart_data['candles'][0]['timestamp'])
        end_dt = datetime.fromisoformat(chart_data['candles'][-1]['timestamp'])
        start_date_str = start_dt.strftime("%Y-%m-%d")
        start_time_str = start_dt.strftime("%H-%M-%S")
        end_date_str = end_dt.strftime("%Y-%m-%d")
        end_time_str = end_dt.strftime("%H-%M-%S")
        filename = f"../inputs/{base_currency.lower()}{quote_currency.lower()}_{interval}_{start_date_str}_{start_time_str}_{end_date_str}_{end_time_str}.json"
    else:
        filename = f"../inputs/{base_currency.lower()}{quote_currency.lower()}_{interval}_nodata.json"
        
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
        
        # Generate filename
        if candles:
            start_dt = datetime.fromisoformat(candles[0]['timestamp'])
            end_dt = datetime.fromisoformat(candles[-1]['timestamp'])
            start_date_str = start_dt.strftime("%Y-%m-%d")
            start_time_str = start_dt.strftime("%H-%M-%S")
            end_date_str = end_dt.strftime("%Y-%m-%d")
            end_time_str = end_dt.strftime("%H-%M-%S")
            filename = f"../inputs/{base_currency.lower()}{quote_currency.lower()}_{interval}_{start_date_str}_{start_time_str}_{end_date_str}_{end_time_str}.json"
        else:
            filename = f"../inputs/{base_currency.lower()}{quote_currency.lower()}_{interval}_nodata.json"
            
        # Ensure data directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(chart_data, f, indent=2)
        
        print(f"Generated {len(candles)} {base_currency}/{quote_currency} synthetic daily candles")
        return True
        
    except Exception as e:
        print(f"Error generating fallback {base_currency}/{quote_currency} data: {e}")
        return False

def download_btc_data(symbol="BTCUSDT", interval="1m", limit=1000, asset_name="Bitcoin", currency="USDT", start_date=None, end_date=None):
    """Download cryptocurrency data from Binance API (alias for download_crypto_data)"""
    return download_crypto_data(symbol, interval, limit, asset_name, currency, start_date, end_date)

def download_eth_data(symbol="ETHUSDT", interval="1m", limit=1000, asset_name="Ethereum", currency="USDT", start_date=None, end_date=None):
    """Download cryptocurrency data from Binance API (alias for download_crypto_data)"""
    return download_crypto_data(symbol, interval, limit, asset_name, currency, start_date, end_date)

