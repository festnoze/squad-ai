import streamlit as st
import pandas as pd
import yfinance as yf
import yfinance as yf
from datetime import date
import plotly.graph_objects as go

def GetPeriodText(period_type, period_value):
    if period_type == 'Minutes':
        period = f"{period_value}m"
    elif period_type == 'Hours':
        period = f"{period_value}h"
    elif period_type == 'Days':
        period = f"{period_value}d"
    elif period_type == 'Months':
        period = f"{period_value}mo"
    else:
        period = f"{period_value}y"
    return period

def GetAiCompanies():
    ai_companies = [
        ("Alphabet Inc.", "GOOGL"),  # Major AI innovations across various fields
        ("Microsoft Corporation", "MSFT"),  # AI in cloud, computing, and more
        ("Amazon.com Inc.", "AMZN"),  # AI in retail, cloud computing
        ("Meta Platforms Inc.", "META"),  # AI in social media, virtual reality
        ("NVIDIA Corporation", "NVDA"),  # Leading in GPUs for AI processing
        ("Tesla Inc.", "TSLA"),  # AI in automotive (self-driving cars)
        ("Baidu Inc.", "BIDU"),  # AI in internet services and products in China
        ("Alibaba Group Holding Limited", "BABA"),  # AI in ecommerce and cloud services
        ("IBM", "IBM"),  # Pioneering in AI, like IBM Watson
        ("Intel Corporation", "INTC"),  # AI chip manufacturing
        ("Advanced Micro Devices, Inc.", "AMD"),  # AI in chip technology
        ("Salesforce.com Inc.", "CRM"),  # AI in customer relationship management
        ("Oracle Corporation", "ORCL"),  # AI in database and enterprise software
        ("SAP SE", "SAP"),  # AI in enterprise application software
        ("Qualcomm Incorporated", "QCOM"),  # AI in telecommunications and semiconductor
        ("Micron Technology, Inc.", "MU"),  # AI in memory and storage solutions
        ("Sony Group Corporation", "SONY"),  # AI in entertainment and electronics
        ("Palantir Technologies Inc.", "PLTR"),  # AI in big data analytics
        ("Twilio Inc.", "TWLO"),  # AI in communication APIs
        ("UiPath Inc.", "PATH"),  # AI in robotic process automation
        ("C3.ai, Inc.", "AI"),  # Enterprise AI software
        ("CrowdStrike Holdings, Inc.", "CRWD"),  # AI in cybersecurity
        ("Snowflake Inc.", "SNOW"),  # AI in cloud-based data warehousing
        ("Zoom Video Communications, Inc.", "ZM"),  # AI in video communications
        ("DocuSign, Inc.", "DOCU")  # AI in electronic agreements and signatures
    ]
    return ai_companies

@st.cache_data
def load_data(ticker, start_date, end_date):
    return yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))

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

st.title('Stock Price App')
st.write("""
# Welcome to the Stock Price App!
*check for any currency or company share*""")

# Streamlit selectbox for user to choose a company
company = st.sidebar.selectbox("Select an AI Company:", GetAiCompanies(), format_func=lambda x: x[0])
tickerSymbol = company[1]

start_date = st.sidebar.date_input('Start Date', max_value= date.today())
end_date = st.sidebar.date_input('End Date', max_value= date.today())

data = load_data(tickerSymbol, start_date, end_date)

plot_candlestick_chart(data, company)

# Display the historical data
st.subheader('Historical Data')

st.write(data, wide=True)
st.write("""end of data""")