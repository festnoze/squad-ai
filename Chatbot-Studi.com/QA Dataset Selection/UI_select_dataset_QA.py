import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

from chatbot_api_client import ChatbotApiClient

class QADatasetSelector:
    
    @staticmethod
    def init_session():
        if 'init' not in st.session_state:
            load_dotenv()
            st.session_state.api_host_uri =  os.getenv("HTTP_SCHEMA") + '://' + os.getenv("EXTERNAL_API_HOST") + ':' + os.getenv("EXTERNAL_API_PORT")
            st.session_state.api_client = ChatbotApiClient(st.session_state.api_host_uri)
            st.session_state['init'] = True
            
    @st.cache_data
    def load_data(path, input_filename) -> pd.DataFrame:
        file_path = path + input_filename
        if not os.path.exists(file_path):
            return pd.DataFrame()
        if '.csv' in input_filename:
            df: pd.DataFrame = pd.read_csv(file_path, sep=';')
        elif '.xlsx' in input_filename: 
            df: pd.DataFrame = pd.read_excel(file_path)
        else:
            raise ValueError("The provided file should be a csv or a xlsx file")
        return df
    
    def create_QA_dataset():
        st.session_state['dataset'] = st.session_state.api_client.create_QA_dataset(int(st.session_state['samples_count_by_metadata']), st.session_state['limited_to_specified_metadata'])

    def run_inference():
        st.session_state['dataset'] = st.session_state.api_client.run_inference(st.session_state['dataset'])
        st.session_state['dataset'] = st.session_state.api_client.evaluate(st.session_state['dataset']) 
    
    def evaluate():
        st.session_state['dataset'] = st.session_state.api_client.evaluate(st.session_state['dataset'])

    def run(args: list):            
        st.set_page_config(layout="wide")

        input_filename: str = "default_input.xslx" if len(args) < 2 else args[1]
        output_filename: str = "default_output.xslx" if len(args) < 3 else args[2]
        path: str = "./outputs/" if len(args) < 4 else args[3]

        df: pd.DataFrame = QADatasetSelector.load_data(path, input_filename)
        if 'select_all' not in st.session_state:
            st.session_state['select_all'] = False
        if 'rows_per_page' not in st.session_state:
            st.session_state['rows_per_page'] = 20
        if 'page_number' not in st.session_state:
            st.session_state['page_number'] = 1

        with st.sidebar:
            st.subheader("💫 Etapes du pipeline d'évaluation")
            st.text_input("Nbr par metadata", key="samples_count_by_metadata", value=10)
            st.text_input("Limiter à cette métadata", key="limited_to_specified_metadata", value=None)
            st.button('🧪 1- Extraire Questions & Réponses du dataset', on_click= QADatasetSelector.create_QA_dataset)
            st.button('✨ 2- RAG : retrieved chunk & réponse générée', on_click=QADatasetSelector.run_inference)
            st.button('✨ 3- Evaluation RAGAS', on_click=QADatasetSelector.evaluate)
            st.divider()

            st.subheader("💫 Actions sur la grille")
            st.button("🔄 Re-démarrage de l'API RAG",               on_click=lambda: st.session_state.api_client.re_init_api())
            st.button('📥 Récupérer données Drupal par json-api',   on_click=lambda: st.session_state.api_client.retrieve_all_data())
            st.button('🌐 Scraping des pages web des formations',   on_click=lambda: st.session_state.api_client.scrape_website_pages())
            st.divider()
            st.button("🗂️ Insertion en base vectorielle : _ Chunking + embedding des documents \nOption: génération synthèse/questions", on_click=lambda: st.session_state.api_client.build_vectorstore())
            st.divider()
            
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
        
        order.extend([col for col in cols if col not in order and 'Unnamed' not in col])
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
            new_rows_per_page: int = st.slider("Rows per page", 30, 200, rows_per_page, key="rows_per_page_slider")
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
                existing_df: pd.DataFrame = pd.read_excel(output_file)
                #existing_df: pd.DataFrame = pd.read_csv(output_file, sep=';')
                combined_df: pd.DataFrame = pd.concat([existing_df, selected_df], ignore_index=True)
            else:
                combined_df: pd.DataFrame = selected_df
            combined_df.to_excel(output_file)
            #combined_df.to_csv(output_file, index=False, sep=';')
            st.success(f"{len(selected_df)} lignes enregistrées sous : '{output_filename}'")