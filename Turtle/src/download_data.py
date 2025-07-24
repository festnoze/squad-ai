import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import time
import random

def download_btc_data(symbol="BTCUSDT", interval="1m", limit=1000, asset_name="Bitcoin", currency="USDT"):
    """Download cryptocurrency data from Binance API
    
    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT, ETHUSDT)
        interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
        limit: Number of candles to download
        asset_name: Display name for the asset
        currency: Quote currency
    """
    url = "https://api.binance.com/api/v3/klines"
    params = urllib.parse.urlencode({
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    })
    full_url = f"{url}?{params}"
    
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
                "period_duration": "1min"
            },
            "candles": candles
        }
        
        # Generate filename with date range
        if candles:
            start_date = datetime.fromtimestamp(data[0][0] / 1000).strftime("%Y%m%d")
            end_date = datetime.fromtimestamp(data[-1][0] / 1000).strftime("%Y%m%d")
            filename = f"data/{symbol.lower()}_{interval}_{start_date}_{end_date}.json"
        else:
            filename = f"data/{symbol.lower()}_{interval}_nodata.json"
            
        with open(filename, 'w') as f:
            json.dump(chart_data, f, indent=2)
        
        print(f"Downloaded {len(candles)} {symbol} {interval} candles")
        return True
        
    except Exception as e:
        print(f"Error downloading {symbol} data: {e}")
        return False

def download_eur_usd_data(base_currency="EUR", quote_currency="USD", limit=100, asset_name="Euro", interval="1m"):
    """Download forex data from exchange rate API and generate synthetic minute data
    
    Args:
        base_currency: Base currency (e.g., EUR, GBP, JPY)
        quote_currency: Quote currency (e.g., USD, EUR)
        limit: Number of candles to generate
        asset_name: Display name for the asset
        interval: Time interval (affects filename only, data is always 1min synthetic)
    """
    # Using a free forex API
    url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
        
        if quote_currency not in data['rates']:
            print(f"Currency pair {base_currency}/{quote_currency} not available")
            return False
        
        # Since this is a simple rate API, we'll create synthetic minute data
        base_rate = data['rates'][quote_currency]
        candles = []
        
        # Generate synthetic data for the specified number of periods
        for i in range(limit):
            timestamp = datetime.now() - timedelta(minutes=limit-i)
            # Add small random variations to simulate real data
            variation = random.uniform(-0.002, 0.002)
            open_price = base_rate + variation
            close_price = base_rate + random.uniform(-0.002, 0.002)
            high_price = max(open_price, close_price) + abs(random.uniform(0, 0.001))
            low_price = min(open_price, close_price) - abs(random.uniform(0, 0.001))
            
            candles.append({
                "timestamp": timestamp.isoformat(),
                "open": round(open_price, 5),
                "high": round(high_price, 5),
                "low": round(low_price, 5),
                "close": round(close_price, 5)
            })
        
        chart_data = {
            "metadata": {
                "asset_name": asset_name,
                "currency": quote_currency,
                "period_duration": "1min"
            },
            "candles": candles
        }
        
        # Generate filename with date range
        if candles:
            start_date = candles[0]['timestamp'][:10].replace('-', '')  # YYYYMMDD format
            end_date = candles[-1]['timestamp'][:10].replace('-', '')   # YYYYMMDD format
            filename = f"data/{base_currency.lower()}{quote_currency.lower()}_{interval}_{start_date}_{end_date}.json"
        else:
            filename = f"data/{base_currency.lower()}{quote_currency.lower()}_{interval}_nodata.json"
            
        with open(filename, 'w') as f:
            json.dump(chart_data, f, indent=2)
        
        print(f"Generated {len(candles)} {base_currency}/{quote_currency} synthetic 1-minute candles")
        return True
        
    except Exception as e:
        print(f"Error downloading {base_currency}/{quote_currency} data: {e}")
        return False

def download_eth_data(symbol="ETHUSDT", interval="1m", limit=1000, asset_name="Ethereum", currency="USDT"):
    """Download cryptocurrency data from Binance API (alias for download_btc_data)
    
    Args:
        symbol: Trading pair symbol (e.g., ETHUSDT, ADAUSDT)
        interval: Time interval (1m, 5m, 15m, 1h, 4h, 12h, 1d, 1w)
        limit: Number of candles to download
        asset_name: Display name for the asset
        currency: Quote currency
    """
    return download_btc_data(symbol, interval, limit, asset_name, currency)

