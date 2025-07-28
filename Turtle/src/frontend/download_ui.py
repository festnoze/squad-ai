import streamlit as st
from datetime import datetime, timedelta
import download_data as dl
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
            if st.button("📥 Download Online Data", type="primary"):
                with st.spinner(f"Downloading {symbol}..."):
                    if dl.download_crypto_data(symbol, interval, limit_param, asset_name, currency, start_date_str, end_date_str):
                        st.success(f"✓ {symbol} downloaded successfully!")
                        st.rerun()
                    else:
                        st.error(f"✗ Failed to download {symbol}")
        
        else:  # Forex
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
            
            interval = st.selectbox(
                "Interval:",
                ["1d"],  # Alpha Vantage free tier only supports daily data
                index=0,
                key="forex_interval",
                help="Free tier supports daily data only"
            )
            
            # Date range option for forex (enabled by default)
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
                with st.spinner(f"Downloading {base_currency}/{quote_currency}..."):
                    if dl.download_eur_usd_data(base_currency, quote_currency, limit_forex_param, asset_name, interval, start_date_forex_str, end_date_forex_str):
                        st.success(f"✓ {base_currency}/{quote_currency} downloaded successfully!")
                        st.rerun()
                    else:
                        st.error(f"✗ Failed to download {base_currency}/{quote_currency}")