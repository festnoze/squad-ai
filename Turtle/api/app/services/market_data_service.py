"""Market data service for downloading cryptocurrency and forex data."""

import json
import os
import random
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from app.models.chart import ChartData, ChartDataRequest, ChartDataResponse, ChartMetadata
from app.models.candle import Candle
from app.core.config import settings


class MarketDataService:
    """Service for downloading and managing market data from various sources."""
    
    def __init__(self):
        self.data_dir = Path(settings.CHART_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_available_sources(self) -> List[Dict]:
        """Get available data sources."""
        return [
            {"name": "binance", "type": "crypto", "description": "Binance cryptocurrency exchange"},
            {"name": "yfinance", "type": "stocks", "description": "Yahoo Finance data"},
            {"name": "alpha_vantage", "type": "stocks", "description": "Alpha Vantage API"},
            {"name": "synthetic", "type": "synthetic", "description": "Generated synthetic data"}
        ]
    
    def get_binance_data(self, symbol: str, interval: str, limit: int = 100) -> List[Candle]:
        """Get Binance data (sync version for tests)."""
        try:
            base_url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            candles = []
            for item in data:
                candle = Candle(
                    timestamp=datetime.fromtimestamp(item[0] / 1000),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5])
                )
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            print(f"Error fetching Binance data: {e}")
            return []
    
    def get_yahoo_data(self, symbol: str, period: str = "1d") -> List[Candle]:
        """Get Yahoo Finance data (sync version for tests)."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = yf.download(symbol, period=period)
            
            if df.empty:
                return []
                
            candles = []
            for idx, row in df.iterrows():
                candle = Candle(
                    timestamp=idx,
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=float(row['Volume'])
                )
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            print(f"Error fetching Yahoo data: {e}")
            return []
    
    def get_alpha_vantage_data(self, symbol: str, function: str = "TIME_SERIES_DAILY") -> List[Candle]:
        """Get Alpha Vantage data (sync version for tests)."""
        try:
            api_key = getattr(settings, 'ALPHA_VANTAGE_API_KEY', 'demo')
            base_url = "https://www.alphavantage.co/query"
            params = {
                "function": function,
                "symbol": symbol,
                "apikey": api_key
            }
            
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            time_series_key = next((k for k in data.keys() if "Time Series" in k), None)
            if not time_series_key:
                return []
                
            candles = []
            for date_str, values in data[time_series_key].items():
                candle = Candle(
                    timestamp=datetime.strptime(date_str, "%Y-%m-%d"),
                    open=float(values.get("1. open", 0)),
                    high=float(values.get("2. high", 0)),
                    low=float(values.get("3. low", 0)),
                    close=float(values.get("4. close", 0)),
                    volume=float(values.get("5. volume", 0))
                )
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            print(f"Error fetching Alpha Vantage data: {e}")
            return []
    
    async def get_synthetic_data(self, symbol: str, days: int = 30) -> List[Candle]:
        """Generate synthetic data for testing."""
        candles = []
        base_price = random.uniform(50, 200)
        
        for i in range(days):
            # Simple random walk
            change = random.uniform(-0.05, 0.05)
            base_price = base_price * (1 + change)
            
            volatility = random.uniform(0.01, 0.03)
            high = base_price * (1 + volatility)
            low = base_price * (1 - volatility)
            open_price = random.uniform(low, high)
            close_price = random.uniform(low, high)
            
            candle = Candle(
                timestamp=datetime.now() - timedelta(days=days-i),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close_price, 2),
                volume=random.uniform(1000, 10000)
            )
            candles.append(candle)
        
        return candles
    
    async def get_chart_data(self, request: ChartDataRequest) -> List[Candle]:
        """Get chart data from specified source."""
        if request.source == "synthetic":
            return await self.get_synthetic_data(request.symbol, request.limit)
        elif request.source == "binance":
            return self.get_binance_data(request.symbol, request.interval, request.limit)
        elif request.source == "yahoo":
            return self.get_yahoo_data(request.symbol)
        elif request.source == "alpha_vantage":
            return self.get_alpha_vantage_data(request.symbol)
        else:
            raise ValueError(f"Unsupported data source: {request.source}")
    
    async def get_latest_price(self, symbol: str, source: str = "synthetic") -> float:
        """Get latest price for a symbol."""
        if source == "synthetic":
            return random.uniform(50, 200)
        elif source == "binance":
            try:
                response = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
                response.raise_for_status()
                data = response.json()
                return float(data["price"])
            except:
                return 100.0
        else:
            raise ValueError(f"Unsupported source: {source}")
    
    async def get_multiple_symbols(self, symbols: List[str], source: str = "synthetic", limit: int = 100) -> Dict[str, List[Candle]]:
        """Get data for multiple symbols."""
        result = {}
        for symbol in symbols:
            request = ChartDataRequest(
                symbol=symbol,
                source=source,
                interval="1d",
                limit=limit
            )
            result[symbol] = await self.get_chart_data(request)
        return result
    
    # Crypto pairs and data sources
    async def get_crypto_pairs(self) -> Dict[str, List[str]]:
        """Get available cryptocurrency trading pairs."""
        return {
            "binance": [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT",
                "SOLUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "SHIBUSDT",
                "LUNAUSDT", "MATICUSDT", "LTCUSDT", "BCHUSDT", "LINKUSDT"
            ]
        }
    
    async def get_forex_pairs(self) -> Dict[str, List[str]]:
        """Get available forex trading pairs."""
        return {
            "alpha_vantage": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD"],
            "yfinance": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "USDCHF", "NZDUSD"],
            "binance": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD"]
        }
    
    # Data download methods
    async def download_crypto_data(self, request: ChartDataRequest, source: str = "binance") -> ChartDataResponse:
        """Download cryptocurrency data from specified source."""
        try:
            if source == "binance":
                success = await self._download_binance_crypto(request)
            elif source == "synthetic":
                success = await self._generate_synthetic_crypto(request)
            else:
                return ChartDataResponse(
                    success=False,
                    message=f"Unknown crypto source: {source}",
                    filename=None,
                    candles_count=0
                )
            
            if success:
                filename = self._generate_filename(request.symbol, request.interval, source)
                candles_count = await self._count_candles_in_file(filename)
                return ChartDataResponse(
                    success=True,
                    message=f"Successfully downloaded {candles_count} candles",
                    filename=filename,
                    candles_count=candles_count
                )
            else:
                return ChartDataResponse(
                    success=False,
                    message="Failed to download data",
                    filename=None,
                    candles_count=0
                )
                
        except Exception as e:
            return ChartDataResponse(
                success=False,
                message=f"Error downloading crypto data: {str(e)}",
                filename=None,
                candles_count=0
            )
    
    async def download_forex_data(self, base_currency: str, quote_currency: str, request: ChartDataRequest) -> ChartDataResponse:
        """Download forex data."""
        try:
            # Try multiple sources in order of preference
            sources = ["yfinance", "alpha_vantage", "synthetic"]
            
            for source in sources:
                try:
                    if source == "yfinance":
                        success = await self._download_yfinance_forex(base_currency, quote_currency, request)
                    elif source == "alpha_vantage":
                        success = await self._download_alpha_vantage_forex(base_currency, quote_currency, request)
                    else:  # synthetic
                        success = await self._generate_synthetic_forex(base_currency, quote_currency, request)
                    
                    if success:
                        symbol = f"{base_currency}{quote_currency}"
                        filename = self._generate_filename(symbol, request.interval, source)
                        candles_count = await self._count_candles_in_file(filename)
                        return ChartDataResponse(
                            success=True,
                            message=f"Successfully downloaded {candles_count} candles from {source}",
                            filename=filename,
                            candles_count=candles_count
                        )
                except Exception as e:
                    print(f"Failed to download from {source}: {e}")
                    continue
            
            return ChartDataResponse(
                success=False,
                message="Failed to download from all sources",
                filename=None,
                candles_count=0
            )
            
        except Exception as e:
            return ChartDataResponse(
                success=False,
                message=f"Error downloading forex data: {str(e)}",
                filename=None,
                candles_count=0
            )
    
    async def generate_synthetic_data(self, symbol: str, interval: str, limit: int, 
                                    volatility: float = 0.02, trend: float = 0.0, 
                                    start_price: float = 100.0) -> ChartDataResponse:
        """Generate synthetic market data for testing."""
        try:
            candles = []
            current_price = start_price
            
            for i in range(limit):
                # Calculate timestamp based on interval
                if interval == "1w":
                    timestamp = datetime.now() - timedelta(weeks=limit-i)
                elif interval == "1d":
                    timestamp = datetime.now() - timedelta(days=limit-i)
                elif interval in ["1h", "4h", "12h"]:
                    hours = int(interval.replace("h", ""))
                    timestamp = datetime.now() - timedelta(hours=hours*(limit-i))
                else:  # minutes
                    minutes = int(interval.replace("m", ""))
                    timestamp = datetime.now() - timedelta(minutes=minutes*(limit-i))
                
                # Generate OHLC with trend and volatility
                variation = random.uniform(-volatility, volatility) + trend
                open_price = current_price
                close_price = current_price * (1 + variation)
                high_price = max(open_price, close_price) * (1 + abs(random.uniform(0, volatility/2)))
                low_price = min(open_price, close_price) * (1 - abs(random.uniform(0, volatility/2)))
                
                candles.append({
                    "timestamp": timestamp.isoformat(),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2)
                })
                
                current_price = close_price
            
            # Sort by timestamp
            candles.sort(key=lambda x: x["timestamp"])
            
            # Create chart data
            chart_data = {
                "metadata": {
                    "asset_name": symbol,
                    "currency": "USD",
                    "period_duration": interval
                },
                "candles": candles
            }
            
            # Save to file
            filename = self._generate_filename(symbol, interval, "synthetic")
            await self._save_chart_data(chart_data, filename)
            
            return ChartDataResponse(
                success=True,
                message=f"Generated {len(candles)} synthetic candles",
                filename=filename,
                candles_count=len(candles)
            )
            
        except Exception as e:
            return ChartDataResponse(
                success=False,
                message=f"Error generating synthetic data: {str(e)}",
                filename=None,
                candles_count=0
            )
    
    async def validate_date_range(self, start_date: str, end_date: str) -> Dict:
        """Validate date range parameters."""
        try:
            if not start_date or not end_date:
                return {"valid": True, "message": "No date range specified"}
                
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            
            if start_dt >= end_dt:
                return {"valid": False, "message": "Start date must be before end date"}
                
            if end_dt > datetime.now():
                return {"valid": False, "message": "End date cannot be in the future"}
                
            if (end_dt - start_dt).days > 5 * 365:
                return {"valid": False, "message": "Date range cannot exceed 5 years"}
                
            return {"valid": True, "message": "Date range is valid"}
            
        except ValueError as e:
            return {"valid": False, "message": f"Invalid date format. Use YYYY-MM-DD format. Error: {e}"}
    
    
    async def get_price_history(self, symbol: str, interval: str, limit: int) -> List[Dict]:
        """Get price history for a symbol."""
        # This would fetch recent price data
        # For now, generate some mock data
        history = []
        current_price = 50000.0 if "BTC" in symbol else 3000.0
        
        for i in range(limit):
            timestamp = datetime.now() - timedelta(hours=i)
            variation = random.uniform(-0.02, 0.02)
            price = current_price * (1 + variation)
            
            history.append({
                "timestamp": timestamp.isoformat(),
                "price": round(price, 2),
                "volume": random.randint(1000, 10000)
            })
            
            current_price = price
        
        return list(reversed(history))  # Oldest first
    
    # Private helper methods
    async def _download_binance_crypto(self, request: ChartDataRequest) -> bool:
        """Download crypto data from Binance API."""
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': request.symbol,
                'interval': request.interval,
                'limit': request.limit or 1000
            }
            
            # Add date range if specified
            if request.start_date and request.end_date:
                start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(request.end_date, "%Y-%m-%d") + timedelta(days=1)
                params['startTime'] = int(start_dt.timestamp() * 1000)
                params['endTime'] = int(end_dt.timestamp() * 1000)
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
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
                    "asset_name": request.symbol,
                    "currency": "USDT",
                    "period_duration": request.interval
                },
                "candles": candles
            }
            
            filename = self._generate_filename(request.symbol, request.interval, "binance")
            await self._save_chart_data(chart_data, filename)
            return True
            
        except Exception as e:
            print(f"Error downloading Binance data: {e}")
            return False
    
    async def _generate_synthetic_crypto(self, request: ChartDataRequest) -> bool:
        """Generate synthetic cryptocurrency data."""
        try:
            candles = []
            base_price = 50000.0 if "BTC" in request.symbol else 3000.0
            
            limit = request.limit or 1000
            for i in range(limit):
                timestamp = datetime.now() - timedelta(hours=limit-i)
                variation = random.uniform(-0.05, 0.05)
                open_price = base_price * (1 + variation)
                close_price = base_price * (1 + random.uniform(-0.05, 0.05))
                high_price = max(open_price, close_price) * (1 + abs(random.uniform(0, 0.02)))
                low_price = min(open_price, close_price) * (1 - abs(random.uniform(0, 0.02)))
                
                candles.append({
                    "timestamp": timestamp.isoformat(),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2)
                })
                
                base_price = close_price
            
            chart_data = {
                "metadata": {
                    "asset_name": request.symbol,
                    "currency": "USDT",
                    "period_duration": request.interval
                },
                "candles": candles
            }
            
            filename = self._generate_filename(request.symbol, request.interval, "synthetic")
            await self._save_chart_data(chart_data, filename)
            return True
            
        except Exception as e:
            print(f"Error generating synthetic crypto data: {e}")
            return False
    
    async def _download_yfinance_forex(self, base_currency: str, quote_currency: str, request: ChartDataRequest) -> bool:
        """Download forex data using yfinance."""
        try:
            # This would require yfinance package
            # For now, fall back to synthetic data
            return await self._generate_synthetic_forex(base_currency, quote_currency, request)
        except Exception:
            return False
    
    async def _download_alpha_vantage_forex(self, base_currency: str, quote_currency: str, request: ChartDataRequest) -> bool:
        """Download forex data from Alpha Vantage."""
        try:
            # This would require Alpha Vantage API key
            # For now, fall back to synthetic data
            return await self._generate_synthetic_forex(base_currency, quote_currency, request)
        except Exception:
            return False
    
    async def _generate_synthetic_forex(self, base_currency: str, quote_currency: str, request: ChartDataRequest) -> bool:
        """Generate synthetic forex data."""
        try:
            candles = []
            # Use different base rates for different currency pairs
            base_rate = 1.1 if base_currency == "EUR" else 1.3 if base_currency == "GBP" else 0.75
            
            limit = request.limit or 100
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
                    "asset_name": f"{base_currency}/{quote_currency}",
                    "currency": quote_currency,
                    "period_duration": request.interval
                },
                "candles": candles
            }
            
            symbol = f"{base_currency}{quote_currency}"
            filename = self._generate_filename(symbol, request.interval, "synthetic")
            await self._save_chart_data(chart_data, filename)
            return True
            
        except Exception as e:
            print(f"Error generating synthetic forex data: {e}")
            return False
    
    def _generate_filename(self, symbol: str, interval: str, source: str) -> str:
        """Generate filename for chart data."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"{symbol.lower()}_{interval}_{source}_{timestamp}.json"
    
    async def _save_chart_data(self, chart_data: Dict, filename: str):
        """Save chart data to file."""
        filepath = self.data_dir / filename
        with open(filepath, 'w') as f:
            json.dump(chart_data, f, indent=2)
    
    async def _count_candles_in_file(self, filename: str) -> int:
        """Count candles in a saved file."""
        try:
            filepath = self.data_dir / filename
            if filepath.exists():
                with open(filepath, 'r') as f:
                    data = json.load(f)
                return len(data.get('candles', []))
            return 0
        except Exception:
            return 0