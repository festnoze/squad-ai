import streamlit as st
import pandas as pd
import sys

st.set_page_config(layout="wide")

input_filename: str = "default_input.csv" if len(sys.argv) < 2 else sys.argv[1]
output_filename: str = "default_output.csv" if len(sys.argv) < 3 else sys.argv[2]
path: str = "./outputs/"

@st.cache_data
def load_data() -> pd.DataFrame:
    df: pd.DataFrame = pd.read_csv(path + input_filename, sep=';')
    return df

df: pd.DataFrame = load_data()
if 'select_all' not in st.session_state:
    st.session_state['select_all'] = False

if st.sidebar.button('Select/Deselect All'):
    st.session_state['select_all'] = not st.session_state['select_all']

rows_per_page: int = st.sidebar.slider("Rows per page", 10, 100, 20)
total_pages: int = len(df) // rows_per_page + (1 if len(df) % rows_per_page > 0 else 0)
page_number: int = st.sidebar.number_input("Page", 1, total_pages, 1)
start_idx: int = (page_number - 1) * rows_per_page
end_idx: int = start_idx + rows_per_page

# Slider for row height multiplier (default row height is 35px)
multiplier: int = st.sidebar.slider("Row height multiplier", 1, 7, 1)
default_row_height: int = 35
custom_row_height: int = multiplier * default_row_height
header_height: int = 50

# Fix container height to always show 'rows_per_page' rows at default height
table_container_height: int = rows_per_page * default_row_height + header_height

df['Select'] = st.session_state['select_all']
cols: list = df.columns.tolist()
cols.insert(0, cols.pop(cols.index('Select')))
df = df[cols]
page_df: pd.DataFrame = df.iloc[start_idx:end_idx].copy()

st.markdown(
    f"""
    <style>
    div[data-testid="stDataEditorGrid"] .grid-row {{
        height: {custom_row_height}px !important;
        min-height: {custom_row_height}px !important;
        max-height: {custom_row_height}px !important;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

edited_df: pd.DataFrame = st.data_editor(
    page_df,
    use_container_width=True,
    height=table_container_height
)

if st.sidebar.button("Save Selected Rows"):
    selected_df: pd.DataFrame = edited_df[edited_df['Select']].copy()
    selected_df.drop(columns=['Select'], inplace=True)
    selected_df.to_csv(output_filename, index=False, sep=';')
    st.sidebar.success(f"{len(selected_df)} rows saved to {output_filename}")
