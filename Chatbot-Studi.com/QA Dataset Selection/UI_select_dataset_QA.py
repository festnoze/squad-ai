import json
import pandas as pd
import os
from dotenv import load_dotenv
import streamlit as st
from streamlit_toggle import st_toggle_switch

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
    
    def load_dataset():
        st.session_state['dataset'] = QADatasetSelector.load_data(st.session_state.path, st.session_state.input_filename)
        if st.session_state['dataset'].empty:
            st.error(f"Le fichier '{st.session_state.input_filename}' est vide ou n'existe pas.")
            return
        # st.session_state['dataset'].dropna(subset=['user_input'], inplace=True)
        # st.session_state['dataset'].dropna(subset=['answer'], inplace=True)
        # st.session_state['dataset'].dropna(subset=['reference'], inplace=True)
        # st.session_state['dataset'].dropna(subset=['category'], inplace=True)
        # st.session_state['dataset']['Select'] = False
    
    def create_QA_dataset():
        response = st.session_state.api_client.create_QA_dataset(int(st.session_state['samples_count_by_metadata']), st.session_state['limited_to_specified_metadata'])
        if response.status_code != 200:
            st.error(f"Erreur lors de la création du dataset de QA: {response.content}")
        else:
            st.session_state['dataset'] = pd.DataFrame(json.loads(response.content))

    def run_inference():
        response = st.session_state.api_client.run_inference(st.session_state['dataset'])
        if response.status_code != 200:
            st.error(f"Erreur lors de la création du dataset de QA: {response.content}")
        else:
            st.session_state['dataset'] = pd.DataFrame(json.loads(response.content))
    
    def evaluate():
        response = st.session_state.api_client.evaluate(st.session_state['dataset'])
        if response.status_code != 200:
            st.error(f"Erreur lors de la création du dataset de QA: {response.content}")
        else:
            content = response.content.decode('utf-8')
            ragas_evaluation_result, ragas_evaluation_link = content
            st.session_state['dataset'] = pd.DataFrame(json.loads(ragas_evaluation_result))
            st.link_button("RAGAS Evaluation", ragas_evaluation_link, "RAGAS Evaluation", "RAGAS Evaluation")

    def save_dataset_to_file():
        selected_df: pd.DataFrame = st.session_state['dataset'][st.session_state['dataset']['Select']].copy()
        selected_df.drop(columns=['Select'], inplace=True)
        output_file: str = st.session_state.path + st.session_state.output_filename
        if os.path.exists(output_file):
            existing_df: pd.DataFrame = pd.read_excel(output_file)
            #existing_df: pd.DataFrame = pd.read_csv(output_file, sep=';')
            combined_df: pd.DataFrame = pd.concat([existing_df, selected_df], ignore_index=True)
        else:
            combined_df: pd.DataFrame = selected_df
        combined_df.to_excel(output_file)
        #combined_df.to_csv(output_file, index=False, sep=';')
        st.success(f"{len(selected_df)} lignes enregistrées sous : '{st.session_state.output_filename}'")

    def invert_selection():
        for index in st.session_state['dataset'].index:
            prev_val = st.session_state['dataset'].at[index, 'Select']
            st.session_state['dataset'].at[index, 'Select'] = not prev_val
        st.session_state['select_all'] = False
        
    def run(args: list):            
        st.set_page_config(layout="wide")
        st.subheader("🧪 Sélection des Questions / Réponses à évaluer")

        st.session_state.input_filename = "default_input.xslx" if len(args) < 2 else args[1]
        st.session_state.output_filename = "default_output.xslx" if len(args) < 3 else args[2]
        st.session_state.path = "./outputs/" if len(args) < 4 else args[3]
        
        if 'dataset' not in st.session_state:
            st.session_state['dataset'] = pd.DataFrame()
        if 'select_all' not in st.session_state:
            st.session_state['select_all'] = False
        if 'rows_per_page' not in st.session_state:
            st.session_state['rows_per_page'] = 20
        if 'page_number' not in st.session_state:
            st.session_state['page_number'] = 1

        with st.sidebar:
            st.markdown(
                """
                <style>
                [data-testid="stSidebar"] {
                    min-width: 400px;
                }
                </style>
                """,
                unsafe_allow_html=True)
            st.subheader("💫 Etapes du processus d'évaluation")
            st.button('🚀 0- Charger dataset existant', on_click= QADatasetSelector.load_dataset)

            col1, col2 = st.columns(2, gap="small")
            with col1:
                st.text_input("Nbr/metadata", key="samples_count_by_metadata", value=10)
            with col2:
                st.text_input("Métadata unique", key="limited_to_specified_metadata", value=None)
            st.button('🚀 1- Générer dataset de Questions & Réponses', on_click= QADatasetSelector.create_QA_dataset)
            st.divider()
            st.button('🔎 2- Sélectionner les éléments à droite ➺', disabled=True)
            
            rows_per_page: int = st.session_state['rows_per_page']
            total_pages: int = len(st.session_state['dataset']) // rows_per_page + (1 if len(st.session_state['dataset']) % rows_per_page > 0 else 0)
            page_number: int = st.session_state['page_number']
            start_idx: int = (page_number - 1) * rows_per_page
            end_idx: int = start_idx + rows_per_page

            new_rows_per_page: int = st.slider("Rows per page", 15, 150, rows_per_page, key="rows_per_page_slider")
            if 'prev_rows_per_page' not in st.session_state or st.session_state['prev_rows_per_page'] != new_rows_per_page:
                st.session_state['page_number'] = 1
                st.session_state['prev_rows_per_page'] = new_rows_per_page
            st.session_state['rows_per_page'] = new_rows_per_page
            total_pages: int = len(st.session_state['dataset']) // new_rows_per_page + (1 if len(st.session_state['dataset']) % new_rows_per_page > 0 else 0)
            col_minus, col_page, col_plus = st.columns([0.5, 1, 0.5], gap="small")
            with col_minus:
                if st.button("⬅️", key="prev_page"):
                    st.session_state['page_number'] = max(1, st.session_state['page_number'] - 1)
                    st.rerun()
            with col_page:
                st.text(f"Page: {st.session_state['page_number']} / {total_pages}")
            with col_plus:
                if st.button("➡️", key="next_page"):
                    st.session_state['page_number'] = min(total_pages, st.session_state['page_number'] + 1)
                    st.rerun()
                        
            col1, col2 = st.columns(2, gap="small")
            with col1:
                st.session_state['select_all'] = st_toggle_switch(
                    label="Sélect. Tout",
                    key="select_all_toggle",
                    default_value=st.session_state['select_all'],
                    label_after=True,                    
                    inactive_color='#306686FF',
                    active_color="#2686BEFF",
                    track_color="#EEEEEE"
                )
            with col2:
                st.button('Inverser sélection', on_click= QADatasetSelector.invert_selection)                    
            st.divider()

            st.button('✨ 3- RAG sur sélection (retrieval & réponse)', on_click=QADatasetSelector.run_inference)
            st.button('🧪 4- Lancer Evaluation RAGAS', on_click=QADatasetSelector.evaluate)
            
            st.text_input(f'Nom du fichier à enregister dans "{st.session_state.path}"', key="output_filename")
            if st.button(f"🗂️ Ajouter les lignes sélectionnées au fichier"):
                QADatasetSelector.save_dataset_to_file()
        
        # sidebar ends

        st.session_state['dataset']['Select'] = st.session_state['select_all']
        cols: list = st.session_state['dataset'].columns.tolist()
        order: list = []

        if "Select" in cols: order.append("Select")
        if "user_input" in cols: order.append("user_input")
        if "answer" in cols: order.append("answer")
        if "reference" in cols: order.append("reference")
        if "category" in cols: order.append("category")
        
        order.extend([col for col in cols if col not in order and 'Unnamed' not in col])
        st.session_state['dataset'] = st.session_state['dataset'][order]

        default_row_height: int = 35
        custom_row_height: int = default_row_height
        header_height: int = 35
        table_container_height: int = rows_per_page * default_row_height + header_height

        page_df: pd.DataFrame = st.session_state['dataset'].iloc[start_idx:end_idx].copy()

        # st.markdown(
        #     f"""
        #     <style>
        #     div[data-testid="stDataEditorGrid"] .grid-row {{
        #         height: {custom_row_height}px !important;
        #         min-height: {custom_row_height}px !important;
        #         max-height: {custom_row_height}px !important;
        #     }}
        #     </style>
        #     """,
        #     unsafe_allow_html=True)

        edited_df: pd.DataFrame = st.data_editor(
            page_df,
            use_container_width=True,
            height=table_container_height
        )
        st.session_state['dataset'].loc[page_df.index] = edited_df