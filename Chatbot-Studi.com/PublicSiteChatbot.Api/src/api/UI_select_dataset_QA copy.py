import streamlit as st
import pandas as pd
import sys

input_filename: str = "default_input.csv" if len(sys.argv) < 2 else sys.argv[1]
output_filename: str = "default_output.csv" if len(sys.argv) < 3 else sys.argv[2]
path :str = "./outputs/"

# Charger le fichier CSV
@st.cache_data
def load_data():
    df = pd.read_csv(path + input_filename, sep=';')
    return df

df = load_data()

# État global pour sélectionner/désélectionner toutes les lignes
if 'select_all' not in st.session_state:
    st.session_state['select_all'] = False

# Bouton pour tout sélectionner / désélectionner
if st.button('Sélectionner/Désélectionner toutes les lignes'):
    st.session_state['select_all'] = not st.session_state['select_all']

# Afficher le DataFrame avec pagination et checkbox
rows_per_page = st.sidebar.slider("Lignes par page", min_value=10, max_value=100, value=20)
total_pages = len(df) // rows_per_page + (1 if len(df) % rows_per_page > 0 else 0)
page_number = st.sidebar.number_input("Page", min_value=1, max_value=total_pages, step=1)
start_idx = (page_number - 1) * rows_per_page
end_idx = start_idx + rows_per_page

# Créer une colonne de sélection
df['Sélectionner'] = st.session_state['select_all']

# Afficher le DataFrame avec la colonne de sélection
st.dataframe(df.iloc[start_idx:end_idx], height=400)

# Bouton pour sauvegarder les lignes sélectionnées
if st.button('Sauvegarder les lignes sélectionnées'):
    selected_rows = df[df['Sélectionner']].copy()
    selected_rows.drop(columns=['Sélectionner'], inplace=True)  # Supprimer la colonne de sélection
    selected_rows.to_csv(output_filename, index=False, sep=';')
    st.success(f"{len(selected_rows)} lignes sauvegardées dans {output_filename}")
