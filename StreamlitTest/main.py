import pandas as pd
import streamlit as st
from datetime import date
import plot_chart as chart
import helper

st.title('Stock Price App')
st.write("""
# Welcome to the Stock Price App!
*check for any currency or company share*""")

# Streamlit selectbox for user to choose a company
companies = helper.GetAiCompanies()
company = st.sidebar.selectbox("Select an AI Company:", companies, format_func=lambda x: x[0])
tickerSymbol = company[1]

start_date = st.sidebar.date_input('Start Date', value=(date.today() - pd.DateOffset(months=6)), max_value=date.today())
end_date = st.sidebar.date_input('End Date', max_value= date.today())
data = helper.LoadData(tickerSymbol, start_date, end_date)

#st.line_chart(data['Close'])
chart.plot_candlestick_chart(data, company)

# Display the historical data
st.subheader('Historical Data')

st.write(data, wide=True)
st.write("""end of data""")