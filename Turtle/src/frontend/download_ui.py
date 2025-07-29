import streamlit as st
from datetime import datetime, timedelta
from download.crypto import download_crypto_data_with_source
from download.forex import download_forex_data
from frontend.trading_pairs import get_crypto_trading_pairs, get_forex_pairs

def render_download_section():
    """Render the collapsible download data section"""
    with st.expander("📥 Download Data", expanded=False):
        # Data source selection
        data_source = st.selectbox(
            "Data Source:",
            ["Cryptocurrency (Binance)", "Forex (Synthetic)"]
        )
        
        if data_source == "Cryptocurrency (Binance)":
            # Crypto source selection
            crypto_source = st.selectbox(
                "Data Source:",
                ["binance", "synthetic"],
                index=0,
                help="Choose data source: Binance API for real data, or synthetic for demo/testing"
            )
            
            # Crypto parameters
            crypto_pairs = get_crypto_trading_pairs()
            crypto_symbols = list(crypto_pairs.keys())
            
            selected_crypto_symbol = st.selectbox(
                "Trading Pair:",
                crypto_symbols,
                index=0,  # Default to BTCUSDT
                help="Select a cryptocurrency trading pair from popular Binance pairs"
            )
            
            # Auto-populate based on selection
            symbol = selected_crypto_symbol
            asset_name = crypto_pairs[selected_crypto_symbol]["asset_name"]
            currency = crypto_pairs[selected_crypto_symbol]["currency"]
            
            # Show the auto-populated values for reference
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**Asset:** {asset_name}")
            with col2:
                st.info(f"**Currency:** {currency}")
            
            interval = st.selectbox(
                "Interval:",
                ["1m", "5m", "15m", "1h", "4h", "12h", "1d", "1w"],
                index=0
            )
            
            # Date range option (enabled by default)
            use_date_range = st.checkbox("Use Date Range", value=True, help="Select specific start and end dates")
            
            if use_date_range:
                # Default to 1 year ending today
                default_end_date = datetime.now().date()
                default_start_date = (datetime.now() - timedelta(days=365)).date()
                
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("Start Date", 
                                             value=default_start_date,
                                             help="Start date for historical data")
                with col2:
                    end_date = st.date_input("End Date", 
                                           value=default_end_date,
                                           help="End date for historical data")
                
                start_date_str = start_date.strftime("%Y-%m-%d") if start_date else None
                end_date_str = end_date.strftime("%Y-%m-%d") if end_date else None
                limit_param = 1000  # Default limit for date range
            else:
                limit_param = st.number_input("Number of Candles:", min_value=1, value=1000)
                start_date_str = None
                end_date_str = None
            
            # Download button for crypto
            if st.button("📥 Download Crypto Data", type="primary"):
                with st.spinner(f"Downloading {symbol} from {crypto_source}..."):
                    if download_crypto_data_with_source(symbol, interval, limit_param, asset_name, currency, start_date_str, end_date_str, crypto_source):
                        st.success(f"✓ {symbol} downloaded successfully from {crypto_source}!")
                        st.rerun()
                    else:
                        st.error(f"✗ Failed to download {symbol} from {crypto_source}")
        
        else:  # Forex
            # Forex source selection
            forex_source = st.selectbox(
                "Data Source:",
                ["alpha_vantage", "yfinance", "binance", "synthetic"],
                index=0,
                key="forex_source_selector",
                help="Choose data source: Alpha Vantage (free tier), yfinance, Binance API, or synthetic data"
            )
            
            # Show source info
            source_info = {
                "alpha_vantage": "📊 Alpha Vantage API - Historical forex data (daily only on free tier)",
                "yfinance": "📈 Yahoo Finance - Wide range of forex pairs",
                "binance": "⚡ Binance API - Real-time data with multiple intervals (requires date range)",
                "synthetic": "🎲 Synthetic Data - Generated data for testing/demo purposes"
            }
            st.info(source_info[forex_source])
            
            # Forex parameters
            forex_pairs = get_forex_pairs()
            forex_symbols = list(forex_pairs.keys())
            
            selected_forex_pair = st.selectbox(
                "Currency Pair:",
                forex_symbols,
                index=0,  # Default to EURUSD
                key="forex_pair_selector",
                help="Select a forex pair from popular currency pairs"
            )
            
            # Auto-populate based on selection
            base_currency = forex_pairs[selected_forex_pair]["base"]
            quote_currency = forex_pairs[selected_forex_pair]["quote"]
            asset_name = forex_pairs[selected_forex_pair]["asset_name"]
            
            # Show the auto-populated values for reference
            col1, col2, col3 = st.columns(3)
            with col1:
                st.info(f"**Base:** {base_currency}")
            with col2:
                st.info(f"**Quote:** {quote_currency}")
            with col3:
                st.info(f"**Asset:** {asset_name}")
            
            # Interval selection based on source
            if forex_source == "alpha_vantage":
                interval_options = ["1d"]
                interval_help = "Alpha Vantage free tier supports daily data only"
            elif forex_source == "binance":
                interval_options = ["1m", "5m", "15m", "1h", "4h", "12h", "1d", "1w"]
                interval_help = "Binance supports multiple intervals"
            else:  # yfinance, synthetic
                interval_options = ["1d", "1wk", "1mo"]
                interval_help = "Available intervals for this source"
            
            interval = st.selectbox(
                "Interval:",
                interval_options,
                index=0,
                key="forex_interval",
                help=interval_help
            )
            
            # Date range option for forex (required for Binance)
            if forex_source == "binance":
                use_date_range_forex = True
                st.info("📅 Date range is required for Binance forex data")
            else:
                use_date_range_forex = st.checkbox("Use Date Range", value=True, key="forex_date_range", help="Select specific start and end dates")
            
            if use_date_range_forex:
                # Default to 1 year ending today
                default_end_date_forex = datetime.now().date()
                default_start_date_forex = (datetime.now() - timedelta(days=365)).date()
                
                col1, col2 = st.columns(2)
                with col1:
                    start_date_forex = st.date_input("Start Date", 
                                                   value=default_start_date_forex,
                                                   key="forex_start_date", 
                                                   help="Start date for historical data")
                with col2:
                    end_date_forex = st.date_input("End Date", 
                                                 value=default_end_date_forex,
                                                 key="forex_end_date", 
                                                 help="End date for historical data")
                
                start_date_forex_str = start_date_forex.strftime("%Y-%m-%d") if start_date_forex else None
                end_date_forex_str = end_date_forex.strftime("%Y-%m-%d") if end_date_forex else None
                limit_forex_param = 100  # Default limit for date range
            else:
                limit_forex_param = st.number_input("Number of Candles:", min_value=1, value=100, key="forex_limit")
                start_date_forex_str = None
                end_date_forex_str = None
            
            # Download button for forex
            if st.button("📥 Download Forex Data", type="primary"):
                with st.spinner(f"Downloading {base_currency}/{quote_currency} from {forex_source}..."):
                    if download_forex_data(base_currency, quote_currency, limit_forex_param, asset_name, interval, start_date_forex_str, end_date_forex_str, forex_source):
                        st.success(f"✓ {base_currency}/{quote_currency} downloaded successfully from {forex_source}!")
                        st.rerun()
                    else:
                        st.error(f"✗ Failed to download {base_currency}/{quote_currency} from {forex_source}")