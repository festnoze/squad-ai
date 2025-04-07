import streamlit as st
import pandas as pd
import sys
import os

st.set_page_config(layout="wide")

input_filename: str = "default_input.xslx" if len(sys.argv) < 2 else sys.argv[1]
output_filename: str = "default_output.xslx" if len(sys.argv) < 3 else sys.argv[2]
path: str = "./outputs/"

@st.cache_data
def load_data() -> pd.DataFrame:
    if '.csv' in input_filename:
        df: pd.DataFrame = pd.read_csv(path + input_filename, sep=';')
    elif '.xlsx' in input_filename: 
        df: pd.DataFrame = pd.read_excel(path + input_filename)
    else:
        raise ValueError("The provided file should be a csv or a xlsx file")
    return df

df: pd.DataFrame = load_data()
if 'select_all' not in st.session_state:
    st.session_state['select_all'] = False
if 'rows_per_page' not in st.session_state:
    st.session_state['rows_per_page'] = 20
if 'page_number' not in st.session_state:
    st.session_state['page_number'] = 1

if st.button('Select/Deselect All'):
    st.session_state['select_all'] = not st.session_state['select_all']

df['Select'] = st.session_state['select_all']
cols: list = df.columns.tolist()
order: list = []

if "Select" in cols: order.append("Select")
if "user_input" in cols: order.append("user_input")
if "answer" in cols: order.append("answer")
if "reference" in cols: order.append("reference")
if "category" in cols: order.append("category")
for col in cols:
    if col not in order:
        order.append(col)
df = df[order]

rows_per_page: int = st.session_state['rows_per_page']
total_pages: int = len(df) // rows_per_page + (1 if len(df) % rows_per_page > 0 else 0)
page_number: int = st.session_state['page_number']
start_idx: int = (page_number - 1) * rows_per_page
end_idx: int = start_idx + rows_per_page

default_row_height: int = 35
custom_row_height: int = default_row_height
header_height: int = 50
table_container_height: int = rows_per_page * default_row_height + header_height

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

col1, col2, col3, col4, col5, col6 = st.columns(6, gap="large")
with col1:
    new_rows_per_page: int = st.slider("Rows per page", 10, 100, rows_per_page, key="rows_per_page_slider")
    if 'prev_rows_per_page' not in st.session_state or st.session_state['prev_rows_per_page'] != new_rows_per_page:
        st.session_state['page_number'] = 1
        st.session_state['prev_rows_per_page'] = new_rows_per_page
    st.session_state['rows_per_page'] = new_rows_per_page
    total_pages: int = len(df) // new_rows_per_page + (1 if len(df) % new_rows_per_page > 0 else 0)
    col_minus, col_page, col_plus = st.columns([0.5, 1, 0.5], gap="small")
    with col_minus:
        if st.button("(-)", key="prev_page"):
            st.session_state['page_number'] = max(1, st.session_state['page_number'] - 1)
    with col_page:
        st.text(f"Page: {st.session_state['page_number']} / {total_pages}")
    with col_plus:
        if st.button("(+)", key="next_page"):
            st.session_state['page_number'] = min(total_pages, st.session_state['page_number'] + 1)

with col2:
    st.empty()
with col3:
    st.empty()
with col4:
    st.empty()
with col5:
    st.empty()
with col6:
    st.empty()

df.loc[page_df.index] = edited_df

if st.button(f"Ajouter les lignes sélectionnées au fichier: '{output_filename}'"):
    selected_df: pd.DataFrame = df[df['Select']].copy()
    selected_df.drop(columns=['Select'], inplace=True)
    output_file: str = path + output_filename
    if os.path.exists(output_file):
        existing_df: pd.DataFrame = pd.read_excel(path + output_file)
        #existing_df: pd.DataFrame = pd.read_csv(output_file, sep=';')
        combined_df: pd.DataFrame = pd.concat([existing_df, selected_df], ignore_index=True)
    else:
        combined_df: pd.DataFrame = selected_df
    combined_df.to_excel(output_file)
    #combined_df.to_csv(output_file, index=False, sep=';')
    st.success(f"{len(selected_df)} lignes enregistrées sous : '{output_filename}'")