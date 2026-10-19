import streamlit as st

from database import init_db

st.set_page_config(page_title="Agenda Pet Shop", layout="wide")
init_db()

paginas = st.navigation(
    {
        "Operação": [
            st.Page("pages/agenda.py", title="Agenda", icon="📅"),
            st.Page("pages/clientes.py", title="Clientes e Pets", icon="🐶"),
            st.Page("pages/servicos.py", title="Serviços", icon="✂️"),
        ],
        "Gestão": [
            st.Page("pages/financeiro.py", title="Financeiro", icon="💰"),
        ],
    }
)
paginas.run()
