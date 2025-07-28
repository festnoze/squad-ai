import streamlit as st
import sys
sys.path.append('..')
from models import ChartData
from src.strategy_engine import StrategyEngine
from src.strategy_loader import StrategyLoader
# Import from new modular files
from chart_utils import load_chart_files, resample_candles, create_candlestick_chart, add_strategy_overlays_to_chart
from download_ui import render_download_section
from sidebar_components import render_chart_selection, render_strategy_section, render_portfolio_info_section
from display_components import render_portfolio_summary, render_asset_metadata, render_trading_signals, render_position_summary, render_data_information


def main():
    """Main Streamlit application"""
    st.set_page_config(
        page_title="Turtle Trading Bot",
        page_icon="🐢",
        layout="wide"
    )
    
    st.title("🐢 Turtle Trading Bot")
    st.markdown("Advanced chart analysis with turtle trading strategy")
    
    # Initialize session state
    if 'strategy_engine' not in st.session_state:
        st.session_state.strategy_engine = StrategyEngine()
        st.session_state.strategy_loader = StrategyLoader()
    if 'run_strategy_triggered' not in st.session_state:
        st.session_state.run_strategy_triggered = False
    
    # Load available chart files
    chart_files = load_chart_files()
    
    # Sidebar for data download and file selection
    with st.sidebar:
        # Render download section
        render_download_section()
        
        st.divider()
        
        # Render chart selection
        selected_file, selected_period = render_chart_selection(chart_files)
        
        st.divider()
        
        # Render portfolio info section
        render_portfolio_info_section()
        
        st.divider()
        
        # Render strategy section
        render_strategy_section()
    
    # Main content area
    if not chart_files:
        st.warning("No chart files found in the 'data' directory. Use the sidebar to download some data files.")
        st.info("Expected format: JSON files with metadata (asset_name, currency, period_duration) and candles data")
        return
    
    if selected_file:
        try:
            # Load chart data
            chart_data = ChartData.from_json_file(selected_file)
            
            # Resample candles if different period selected
            resampled_candles = resample_candles(chart_data.candles, selected_period)
            
            # Create new chart data with resampled candles
            resampled_chart_data = ChartData(
                metadata=chart_data.metadata,
                candles=resampled_candles
            )
            
            # Handle strategy execution on full chart
            symbol = chart_data.metadata.asset_name.upper()
            signals = []
            
            # Check if run strategy was triggered
            if st.session_state.run_strategy_triggered and hasattr(st.session_state, 'run_strategy'):
                # Reset portfolio with user-defined balance and currency
                st.session_state.strategy_engine.reset_portfolio()
                
                # Update portfolio with user settings
                portfolio_summary = st.session_state.strategy_engine.get_portfolio_summary()
                portfolio_summary['current_balance'] = st.session_state.portfolio_balance
                portfolio_summary['initial_balance'] = st.session_state.portfolio_balance
                
                # Load and run the selected strategy on full chart data
                st.session_state.strategy_engine.load_strategy(st.session_state.run_strategy)
                st.session_state.strategy_engine.enable_trading(True)
                
                # Process all data with the strategy
                signals = st.session_state.strategy_engine.process_market_data(symbol, resampled_chart_data)
                
                # Clear the trigger
                st.session_state.run_strategy_triggered = False
                
                st.success(f"Strategy execution completed! Processed {len(resampled_chart_data.candles)} candles with portfolio balance of {st.session_state.portfolio_currency} {st.session_state.portfolio_balance:,.2f}")
            
            # Process with strategy engine if enabled (normal operation)
            elif st.session_state.strategy_engine.strategy_config:
                signals = st.session_state.strategy_engine.process_market_data(symbol, resampled_chart_data)
            
            # Render portfolio summary
            render_portfolio_summary()
            
            # Render asset metadata
            render_asset_metadata(chart_data, selected_period)
            
            # Display chart
            fig = create_candlestick_chart(resampled_chart_data)
            
            # Add strategy signals to chart if available
            add_strategy_overlays_to_chart(fig, symbol)
            
            # Update title to show current period
            fig.update_layout(
                title=f"{chart_data.metadata.asset_name} ({chart_data.metadata.currency}) - {selected_period}"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Render trading signals
            render_trading_signals(signals)
            
            # Render position summary
            render_position_summary(symbol)
            
            # Render data information
            render_data_information(chart_data, resampled_candles, selected_period, symbol)
            
        except Exception as e:
            st.error(f"Error loading chart file: {str(e)}")


if __name__ == "__main__":
    main()