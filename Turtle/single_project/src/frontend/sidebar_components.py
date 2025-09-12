"""Main sidebar UI components for the application."""

import streamlit as st
import sys
sys.path.append('..')
from models import ChartData
from chart_utils import format_filename
from period_utils import get_valid_periods, get_period_index


def render_chart_selection(chart_files):
    """Render chart file selection section"""
    with st.expander("📊 Select Chart", expanded=True):
        if chart_files:
            selected_file = st.selectbox(
                "Select a chart file:",
                chart_files,
                format_func=format_filename
            )
            
            # Load chart data to get native period
            native_period = "1min"  # Default
            if selected_file:
                try:
                    from models import ChartData
                    chart_data = ChartData.from_json_file(selected_file)
                    native_period = chart_data.metadata.period_duration
                except Exception as e:
                    st.warning(f"Could not read chart metadata: {e}")
            
            # Period selection with validation
            st.subheader("⏱️ Time Period")
            valid_periods = get_valid_periods(native_period)
            
            # Show native period info
            st.info(f"📈 Period: **{native_period}** (can be upsampled higher)")
            
            # Set default to native period
            default_index = get_period_index(native_period, valid_periods)
            
            selected_period = st.selectbox(
                "Select time period:",
                valid_periods,
                index=default_index,
                help=f"Native period is {native_period}. You can only select equal or higher timeframes."
            )
            
            return selected_file, selected_period
        else:
            st.warning("No chart files found. Download some data first.")
            return None, "1min"


def render_portfolio_info_section():
    """Render portfolio configuration section"""
    with st.expander("💰 Portfolio Settings", expanded=False):
        # Initialize session state for portfolio settings
        if 'portfolio_balance' not in st.session_state:
            st.session_state.portfolio_balance = 100000.0
        if 'portfolio_currency' not in st.session_state:
            st.session_state.portfolio_currency = "USD"
        
        # Portfolio balance input
        portfolio_balance = st.number_input(
            "Portfolio Balance:",
            min_value=1000.0,
            value=st.session_state.portfolio_balance,
            step=1000.0,
            format="%.2f"
        )
        st.session_state.portfolio_balance = portfolio_balance
        
        # Currency dropdown
        currency_options = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "BTC", "ETH", "USDT"]
        portfolio_currency = st.selectbox(
            "Portfolio Currency:",
            currency_options,
            index=currency_options.index(st.session_state.portfolio_currency)
        )
        st.session_state.portfolio_currency = portfolio_currency
        
        # Strategy selection for running
        strategies = st.session_state.strategy_loader.load_all_strategies()
        if strategies:
            strategy_names = ["Select Strategy..."] + [s.name for s in strategies]
            selected_strategy_name = st.selectbox(
                "Strategy to Run:",
                strategy_names,
                key="run_strategy_select"
            )
            
            # Run strategy button
            if selected_strategy_name != "Select Strategy...":
                if st.button("🚀 Run Strategy on Full Chart", type="primary", use_container_width=True):
                    selected_strategy = st.session_state.strategy_loader.get_strategy_by_name(selected_strategy_name)
                    if selected_strategy:
                        # Store the strategy to run for later processing
                        st.session_state.run_strategy = selected_strategy
                        st.session_state.run_strategy_triggered = True
                        st.success(f"Running {selected_strategy_name} on full chart data...")
                        st.rerun()
        else:
            st.warning("No strategies available")


def render_strategy_section():
    """Render trading strategy selection section"""
    with st.expander("🐢 Trading Strategy", expanded=False):
        strategies = st.session_state.strategy_loader.load_all_strategies()
        
        if strategies:
            strategy_names = ["None"] + [s.name for s in strategies]
            selected_strategy_name = st.selectbox(
                "Select strategy:",
                strategy_names
            )
            
            if selected_strategy_name != "None":
                selected_strategy = st.session_state.strategy_loader.get_strategy_by_name(selected_strategy_name)
                if selected_strategy:
                    st.session_state.strategy_engine.load_strategy(selected_strategy)
                    st.success(f"✓ {selected_strategy_name} loaded")
                    
                    # Strategy controls
                    trading_enabled = st.checkbox("Enable Trading", value=st.session_state.strategy_engine.is_enabled)
                    st.session_state.strategy_engine.enable_trading(trading_enabled)
                    
                    if st.button("Reset Portfolio"):
                        st.session_state.strategy_engine.reset_portfolio()
                        st.success("Portfolio reset to $100,000")
                        st.rerun()
            else:
                st.session_state.strategy_engine.load_strategy(None)
        else:
            st.warning("No strategies found in strategies/ directory")