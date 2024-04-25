import plotly.graph_objects as go
import streamlit as st

def plot_candlestick_chart(data, company):
    # Plotting the candlestick chart
    fig = go.Figure(data=[go.Candlestick(
        x=data.index,
        open=data.Open,
        high=data.High,
        low=data.Low,
        close=data.Close,
        name='Candlestick'
    )])

    # Update the layout
    fig.update_layout(
        title=f'Candlestick chart for {company[0]}',
        xaxis_title='Date',
        yaxis_title='Price',
        xaxis_rangeslider_visible=False  # Hide the range slider
    )

    st.plotly_chart(fig, use_container_width=True)
