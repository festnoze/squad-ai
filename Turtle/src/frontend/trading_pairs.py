"""Trading pair configurations for different data sources."""


def get_crypto_trading_pairs():
    """Get list of popular cryptocurrency trading pairs for Binance"""
    return {
        # Major Bitcoin pairs
        "BTCUSDT": {"asset_name": "Bitcoin", "currency": "USDT"},
        "BTCBUSD": {"asset_name": "Bitcoin", "currency": "BUSD"},
        "BTCETH": {"asset_name": "Bitcoin", "currency": "ETH"},
        
        # Major Ethereum pairs
        "ETHUSDT": {"asset_name": "Ethereum", "currency": "USDT"},
        "ETHBUSD": {"asset_name": "Ethereum", "currency": "BUSD"},
        "ETHBTC": {"asset_name": "Ethereum", "currency": "BTC"},
        
        # Other major cryptocurrencies
        "ADAUSDT": {"asset_name": "Cardano", "currency": "USDT"},
        "BNBUSDT": {"asset_name": "Binance Coin", "currency": "USDT"},
        "XRPUSDT": {"asset_name": "Ripple", "currency": "USDT"},
        "SOLUSDT": {"asset_name": "Solana", "currency": "USDT"},
        "DOTUSDT": {"asset_name": "Polkadot", "currency": "USDT"},
        "AVAXUSDT": {"asset_name": "Avalanche", "currency": "USDT"},
        "MATICUSDT": {"asset_name": "Polygon", "currency": "USDT"},
        "LINKUSDT": {"asset_name": "Chainlink", "currency": "USDT"},
        "UNIUSDT": {"asset_name": "Uniswap", "currency": "USDT"},
        
        # Meme coins
        "DOGEUSDT": {"asset_name": "Dogecoin", "currency": "USDT"},
        "SHIBUSDT": {"asset_name": "Shiba Inu", "currency": "USDT"},
        
        # DeFi tokens
        "AAVEUSDT": {"asset_name": "Aave", "currency": "USDT"},
        "COMPUSDT": {"asset_name": "Compound", "currency": "USDT"},
    }


def get_forex_pairs():
    """Get list of popular forex pairs"""
    return {
        # Major pairs
        "EURUSD": {"base": "EUR", "quote": "USD", "asset_name": "Euro"},
        "GBPUSD": {"base": "GBP", "quote": "USD", "asset_name": "British Pound"},
        "USDJPY": {"base": "USD", "quote": "JPY", "asset_name": "US Dollar"},
        "USDCHF": {"base": "USD", "quote": "CHF", "asset_name": "US Dollar"},
        "AUDUSD": {"base": "AUD", "quote": "USD", "asset_name": "Australian Dollar"},
        "USDCAD": {"base": "USD", "quote": "CAD", "asset_name": "US Dollar"},
        "NZDUSD": {"base": "NZD", "quote": "USD", "asset_name": "New Zealand Dollar"},
        
        # Cross pairs
        "EURGBP": {"base": "EUR", "quote": "GBP", "asset_name": "Euro"},
        "EURJPY": {"base": "EUR", "quote": "JPY", "asset_name": "Euro"},
        "GBPJPY": {"base": "GBP", "quote": "JPY", "asset_name": "British Pound"},
        "CHFJPY": {"base": "CHF", "quote": "JPY", "asset_name": "Swiss Franc"},
        "EURCHF": {"base": "EUR", "quote": "CHF", "asset_name": "Euro"},
        "AUDCAD": {"base": "AUD", "quote": "CAD", "asset_name": "Australian Dollar"},
        "CADCHF": {"base": "CAD", "quote": "CHF", "asset_name": "Canadian Dollar"},
        "NZDCAD": {"base": "NZD", "quote": "CAD", "asset_name": "New Zealand Dollar"},
        
        # Exotic pairs
        "USDZAR": {"base": "USD", "quote": "ZAR", "asset_name": "US Dollar"},
        "USDTRY": {"base": "USD", "quote": "TRY", "asset_name": "US Dollar"},
        "USDBRL": {"base": "USD", "quote": "BRL", "asset_name": "US Dollar"},
    }