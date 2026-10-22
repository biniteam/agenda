import streamlit as st

from database import (
    excluir_servico,
    init_db,
    listar_servicos,
    obter_servico,
    salvar_servico,
)
from utils import formatar_moeda

init_db()

st.title("Serviços")

if "servico_edit_id" not in st.session_state:
    st.session_state.servico_edit_id = None

servicos = listar_servicos()

col_lista, col_form = st.columns((1.2, 1))

with col_lista:
    st.subheader("Serviços cadastrados")
    if not servicos:
        st.info("Nenhum serviço cadastrado ainda.")
    for servico in servicos:
        with st.container(border=True):
            st.markdown(f"**{servico['nome']}**")
            st.caption(
                f"Preço padrão: {formatar_moeda(servico['preco_padrao'])} · "
                f"Duração estimada: {servico['duracao_minutos']} min"
            )
            b1, b2 = st.columns(2)
            if b1.button("Editar", key=f"edit_serv_{servico['id']}"):
                st.session_state.servico_edit_id = servico["id"]
                st.rerun()
            if b2.button("Excluir", key=f"del_serv_{servico['id']}"):
                sucesso, msg = excluir_servico(servico["id"])
                if sucesso:
                    if st.session_state.servico_edit_id == servico["id"]:
                        st.session_state.servico_edit_id = None
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with col_form:
    editando = (
        obter_servico(st.session_state.servico_edit_id)
        if st.session_state.servico_edit_id
        else None
    )
    st.subheader("Editar serviço" if editando else "Novo serviço")
    with st.form("form_servico", clear_on_submit=editando is None):
        nome = st.text_input("Nome do serviço", value=editando["nome"] if editando else "")
        preco_padrao = st.number_input(
            "Preço padrão (R$)",
            min_value=0.0,
            value=float(editando["preco_padrao"]) if editando else 50.0,
            step=5.0,
        )
        duracao_minutos = st.number_input(
            "Duração estimada (minutos)",
            min_value=5,
            value=int(editando["duracao_minutos"]) if editando else 60,
            step=5,
        )
        salvar = st.form_submit_button("Salvar serviço", type="primary")
        cancelar = st.form_submit_button("Cancelar edição") if editando else False

    if cancelar:
        st.session_state.servico_edit_id = None
        st.rerun()

    if salvar:
        if not nome.strip():
            st.error("Informe o nome do serviço.")
        else:
            salvar_servico(
                nome=nome,
                preco_padrao=preco_padrao,
                duracao_minutos=duracao_minutos,
                servico_id=editando["id"] if editando else None,
            )
            st.session_state.servico_edit_id = None
            st.success("Serviço salvo com sucesso.")
            st.rerun()
