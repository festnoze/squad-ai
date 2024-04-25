
import streamlit as st
import yfinance as yf

@st.cache_data
def LoadData(ticker, start_date, end_date):
    return yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))


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
