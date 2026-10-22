from datetime import date

import streamlit as st

from database import (
    excluir_cliente,
    excluir_pet,
    init_db,
    listar_clientes,
    listar_pets,
    obter_cliente,
    obter_pet,
    prontuario_pet,
    salvar_cliente,
    salvar_pet,
)
from utils import PORTES, formatar_moeda, hoje

init_db()

st.title("Clientes e Pets")

if "cliente_edit_id" not in st.session_state:
    st.session_state.cliente_edit_id = None
if "pet_edit_id" not in st.session_state:
    st.session_state.pet_edit_id = None

clientes = listar_clientes()
pets = listar_pets()
clientes_map = {c["id"]: c["nome"] for c in clientes}

tab_clientes, tab_pets, tab_prontuario = st.tabs(
    ["Tutores", "Pets", "Prontuário estético"]
)

with tab_clientes:
    col_lista, col_form = st.columns((1.2, 1))
    with col_lista:
        st.subheader("Tutores cadastrados")
        if not clientes:
            st.info("Nenhum tutor cadastrado ainda.")
        for cliente in clientes:
            with st.container(border=True):
                st.markdown(f"**{cliente['nome']}**")
                st.caption(
                    f"{cliente['telefone'] or 'Sem telefone'} · "
                    f"{cliente['qtd_pets']} pet(s)"
                )
                if cliente["endereco"]:
                    st.caption(cliente["endereco"])
                b1, b2 = st.columns(2)
                if b1.button("Editar", key=f"edit_cli_{cliente['id']}"):
                    st.session_state.cliente_edit_id = cliente["id"]
                    st.rerun()
                if b2.button("Excluir", key=f"del_cli_{cliente['id']}"):
                    excluir_cliente(cliente["id"])
                    if st.session_state.cliente_edit_id == cliente["id"]:
                        st.session_state.cliente_edit_id = None
                    st.rerun()

    with col_form:
        editando = obter_cliente(st.session_state.cliente_edit_id) if st.session_state.cliente_edit_id else None
        st.subheader("Editar tutor" if editando else "Novo tutor")
        with st.form("form_cliente", clear_on_submit=editando is None):
            nome = st.text_input("Nome", value=editando["nome"] if editando else "")
            telefone = st.text_input(
                "Telefone / WhatsApp",
                value=editando["telefone"] if editando else "",
                placeholder="11999999999",
            )
            endereco = st.text_input(
                "Endereço", value=editando["endereco"] if editando else ""
            )
            observacoes = st.text_area(
                "Observações",
                value=editando["observacoes"] if editando else "",
            )
            salvar = st.form_submit_button("Salvar tutor", type="primary")
            cancelar = st.form_submit_button("Cancelar edição") if editando else False
        if cancelar:
            st.session_state.cliente_edit_id = None
            st.rerun()
        if salvar:
            if not nome.strip():
                st.error("Informe o nome do tutor.")
            else:
                salvar_cliente(
                    nome=nome,
                    telefone=telefone,
                    endereco=endereco,
                    observacoes=observacoes,
                    cliente_id=editando["id"] if editando else None,
                )
                st.session_state.cliente_edit_id = None
                st.success("Tutor salvo.")
                st.rerun()

with tab_pets:
    if not clientes:
        st.warning("Cadastre um tutor antes de incluir pets.")
    else:
        col_lista, col_form = st.columns((1.2, 1))
        with col_lista:
            st.subheader("Pets cadastrados")
            if not pets:
                st.info("Nenhum pet cadastrado ainda.")
            for pet in pets:
                with st.container(border=True):
                    st.markdown(f"**{pet['nome']}** · {pet['tutor_nome']}")
                    detalhes = [
                        pet["especie"] or "Espécie n/d",
                        pet["raca"] or "Raça n/d",
                        f"Porte {pet['porte'] or '-'}",
                    ]
                    if pet["pelagem"]:
                        detalhes.append(pet["pelagem"])
                    st.caption(" · ".join(detalhes))
                    if pet["temperamento"] or pet["alergias_restricoes"]:
                        st.caption(
                            f"Temperamento: {pet['temperamento'] or '-'} · "
                            f"Alergias: {pet['alergias_restricoes'] or '-'}"
                        )
                    b1, b2 = st.columns(2)
                    if b1.button("Editar", key=f"edit_pet_{pet['id']}"):
                        st.session_state.pet_edit_id = pet["id"]
                        st.rerun()
                    if b2.button("Excluir", key=f"del_pet_{pet['id']}"):
                        excluir_pet(pet["id"])
                        if st.session_state.pet_edit_id == pet["id"]:
                            st.session_state.pet_edit_id = None
                        st.rerun()

        with col_form:
            editando = obter_pet(st.session_state.pet_edit_id) if st.session_state.pet_edit_id else None
            st.subheader("Editar pet" if editando else "Novo pet")
            ids_clientes = [c["id"] for c in clientes]
            indice_tutor = 0
            if editando and editando["cliente_id"] in ids_clientes:
                indice_tutor = ids_clientes.index(editando["cliente_id"])
            nascimento_valor = None
            if editando and editando["data_nascimento"]:
                nascimento_valor = date.fromisoformat(editando["data_nascimento"][:10])
            with st.form("form_pet", clear_on_submit=editando is None):
                tutor_id = st.selectbox(
                    "Tutor",
                    options=ids_clientes,
                    index=indice_tutor,
                    format_func=lambda cid: clientes_map[cid],
                )
                nome = st.text_input("Nome", value=editando["nome"] if editando else "")
                c1, c2 = st.columns(2)
                especie = c1.text_input(
                    "Espécie", value=editando["especie"] if editando else "Cão"
                )
                raca = c2.text_input("Raça", value=editando["raca"] if editando else "")
                porte_atual = editando["porte"] if editando and editando["porte"] in PORTES else "M"
                porte = st.selectbox("Porte", PORTES, index=PORTES.index(porte_atual))
                pelagem = st.text_input(
                    "Pelagem", value=editando["pelagem"] if editando else ""
                )
                data_nascimento = st.date_input(
                    "Data de nascimento",
                    value=nascimento_valor or hoje(),
                    max_value=hoje(),
                    format="DD/MM/YYYY",
                )
                tem_nascimento = st.checkbox(
                    "Informar data de nascimento",
                    value=bool(editando and editando["data_nascimento"]),
                )
                temperamento = st.text_input(
                    "Temperamento / comportamento",
                    value=editando["temperamento"] if editando else "",
                    placeholder="Ex.: Dócil, medroso no secador",
                )
                alergias = st.text_area(
                    "Alergias / restrições médicas",
                    value=editando["alergias_restricoes"] if editando else "",
                )
                salvar = st.form_submit_button("Salvar pet", type="primary")
                cancelar = st.form_submit_button("Cancelar edição") if editando else False
            if cancelar:
                st.session_state.pet_edit_id = None
                st.rerun()
            if salvar:
                if not nome.strip():
                    st.error("Informe o nome do pet.")
                else:
                    salvar_pet(
                        cliente_id=tutor_id,
                        nome=nome,
                        especie=especie,
                        raca=raca,
                        porte=porte,
                        pelagem=pelagem,
                        data_nascimento=data_nascimento if tem_nascimento else None,
                        temperamento=temperamento,
                        alergias_restricoes=alergias,
                        pet_id=editando["id"] if editando else None,
                    )
                    st.session_state.pet_edit_id = None
                    st.success("Pet salvo.")
                    st.rerun()

with tab_prontuario:
    if not pets:
        st.info("Cadastre um pet para ver o histórico de banhos e tosas.")
    else:
        pet_ids = [p["id"] for p in pets]
        pet_escolhido = st.selectbox(
            "Pet",
            options=pet_ids,
            format_func=lambda pid: next(
                f"{p['nome']} ({p['tutor_nome']})" for p in pets if p["id"] == pid
            ),
        )
        historico = prontuario_pet(pet_escolhido)
        pet = next(p for p in pets if p["id"] == pet_escolhido)
        st.markdown(
            f"**{pet['nome']}** · Tutor: {pet['tutor_nome']} · "
            f"Alergias: {pet['alergias_restricoes'] or 'nenhuma registrada'}"
        )
        if not historico:
            st.info("Ainda não há serviços registrados para este pet.")
        for item in historico:
            with st.container(border=True):
                st.markdown(
                    f"**{item['data_hora'][:16]}** · {item['servico_nome']} · "
                    f"{item['status']}"
                )
                st.caption(
                    f"Profissional: {item['profissional'] or '-'} · "
                    f"Valor: {formatar_moeda(item['valor_estimado'])}"
                )
                if item["observacoes"]:
                    st.write(item["observacoes"])
