"""
Download package for Turtle Trading Bot

This package contains modules for downloading financial data from various sources:
- crypto.py: Cryptocurrency data from Binance API
- forex.py: Forex data from Alpha Vantage and fallback sources
"""

from .crypto import (
    download_crypto_data,
    download_btc_data, 
    download_eth_data,
    download_crypto_data_with_source
)

from .forex import (
    download_eur_usd_data,
    yfinance_forex_data,
    download_binance_forex_data,
    download_forex_data
)

__all__ = [
    'download_crypto_data',
    'download_btc_data',
    'download_eth_data',
    'download_crypto_data_with_source',
    'download_eur_usd_data',
    'yfinance_forex_data',
    'download_binance_forex_data',
    'download_forex_data'
]