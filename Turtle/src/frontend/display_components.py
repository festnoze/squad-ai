"""Display and information components for the main interface."""

import streamlit as st


def render_portfolio_summary():
    """Render portfolio summary metrics"""
    if st.session_state.strategy_engine.strategy_config:
        portfolio_summary = st.session_state.strategy_engine.get_portfolio_summary()
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Balance", f"${portfolio_summary['current_balance']:,.2f}")
        with col2:
            st.metric("Equity", f"${portfolio_summary['equity']:,.2f}")
        with col3:
            st.metric("Total P&L", f"${portfolio_summary['total_pnl']:,.2f}")
        with col4:
            st.metric("Open Trades", portfolio_summary['open_trades'])
        with col5:
            st.metric("Win Rate", f"{portfolio_summary['win_rate']:.1%}")


def render_asset_metadata(chart_data, selected_period):
    """Render asset metadata metrics"""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Asset", chart_data.metadata.asset_name)
    with col2:
        st.metric("Currency", chart_data.metadata.currency)
    with col3:
        st.metric("Original Period", chart_data.metadata.period_duration)
    with col4:
        st.metric("Display Period", selected_period)


def render_trading_signals(signals):
    """Render recent trading signals"""
    if signals:
        st.subheader("📈 Recent Trading Signals")
        for signal in signals[-5:]:  # Show last 5 signals
            signal_color = "🟢" if signal.trade_type.value == "long" else "🔴"
            st.write(f"{signal_color} **{signal.signal_type.upper()}** {signal.trade_type.value} at ${signal.price:.2f} - {signal.reason}")


def render_position_summary(symbol):
    """Render position summary for a symbol"""
    if st.session_state.strategy_engine.strategy_config:
        position_summary = st.session_state.strategy_engine.get_position_summary(symbol)
        if position_summary.get('open_positions', 0) > 0:
            st.subheader("📊 Position Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Open Positions", position_summary['open_positions'])
            with col2:
                st.metric("Total Units", position_summary['total_units'])
            with col3:
                st.metric("Unrealized P&L", f"${position_summary['unrealized_pnl']:.2f}")


def render_data_information(chart_data, resampled_candles, selected_period, symbol):
    """Render data information section"""
    st.subheader("📋 Data Information")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"Original candles: {len(chart_data.candles)}")
        st.write(f"Displayed candles ({selected_period}): {len(resampled_candles)}")
    with col2:
        if resampled_candles:
            st.write(f"Date range: {resampled_candles[0].timestamp.strftime('%Y-%m-%d')} to {resampled_candles[-1].timestamp.strftime('%Y-%m-%d')}")
        if st.session_state.strategy_engine.strategy_config and symbol in st.session_state.strategy_engine.position_manager.market_data:
            market_data = st.session_state.strategy_engine.position_manager.market_data[symbol]
            st.write(f"Current ATR: {market_data.atr:.4f}")