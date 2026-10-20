import calendar
from datetime import date, datetime, time, timedelta

import streamlit as st

from database import (
    adicionar_excecao_agendamento,
    aniversariantes_do_dia,
    atualizar_pago_agendamento,
    atualizar_status_agendamento,
    excluir_agendamento,
    listar_agendamentos,
    listar_pets,
    listar_servicos,
    obter_agendamento,
    salvar_agendamento,
    totais_por_dia,
)
from utils import (
    DIAS_SEMANA,
    STATUS_AGENDAMENTO,
    construir_rrule,
    decodificar_rrule,
    formatar_moeda,
    fim_semana,
    hoje,
    inicio_semana,
    link_whatsapp,
    rotulo_mes,
)

calendar.setfirstweekday(calendar.MONDAY)

st.title("Agenda")

if "agenda_nivel" not in st.session_state:
    st.session_state.agenda_nivel = "mes"
if "agenda_data" not in st.session_state:
    st.session_state.agenda_data = hoje()
if "agendamento_edit_id" not in st.session_state:
    st.session_state.agendamento_edit_id = None


def ir_para(nivel: str, dia: date | None = None) -> None:
    st.session_state.agenda_nivel = nivel
    if dia is not None:
        st.session_state.agenda_data = dia
    st.rerun()


referencia: date = st.session_state.agenda_data
nivel = st.session_state.agenda_nivel

nav1, nav2, nav3, nav4 = st.columns((2, 1, 1, 2))
if nav1.button("Mês", type="primary" if nivel == "mes" else "secondary"):
    ir_para("mes")
if nav2.button("Semana", type="primary" if nivel == "semana" else "secondary"):
    ir_para("semana")
if nav3.button("Dia", type="primary" if nivel == "dia" else "secondary"):
    ir_para("dia")
with nav4:
    escolhida = st.date_input(
        "Data de referência",
        value=referencia,
        format="DD/MM/YYYY",
        label_visibility="collapsed",
    )
    if escolhida != referencia:
        ir_para(nivel, escolhida)

st.caption(f"Nível atual: {nivel} · referência {referencia.strftime('%d/%m/%Y')}")


def formulario_agendamento(dia_padrao: date) -> None:
    pets = listar_pets()
    servicos = listar_servicos()
    if not pets or not servicos:
        st.warning("Cadastre pelo menos um pet e um serviço para agendar.")
        return

    editando = (
        obter_agendamento(st.session_state.agendamento_edit_id)
        if st.session_state.agendamento_edit_id
        else None
    )
    pet_ids = [p["id"] for p in pets]
    servico_ids = [s["id"] for s in servicos]
    pet_index = 0
    servico_index = 0
    if editando and editando["pet_id"] in pet_ids:
        pet_index = pet_ids.index(editando["pet_id"])
    if editando and editando["servico_id"] in servico_ids:
        servico_index = servico_ids.index(editando["servico_id"])

    data_valor = dia_padrao
    hora_valor = time(9, 0)
    if editando:
        dt = datetime.strptime(editando["data_hora"][:16], "%Y-%m-%d %H:%M")
        data_valor = dt.date()
        hora_valor = dt.time()

    status_atual = editando["status"] if editando else "Agendado"
    status_index = (
        STATUS_AGENDAMENTO.index(status_atual)
        if status_atual in STATUS_AGENDAMENTO
        else 0
    )
    valores_servico = {s["id"]: float(s["preco_padrao"]) for s in servicos}

    # Configurações de recorrência padrão
    config_rrule = decodificar_rrule(editando["rrule"] if editando else None)

    titulo = "Editar agendamento (Série)" if editando else "Novo agendamento"
    with st.expander(titulo, expanded=bool(editando)):
        with st.container(border=True):
            pet_id = st.selectbox(
                "Pet",
                options=pet_ids,
                index=pet_index,
                format_func=lambda pid: next(
                    f"{p['nome']} ({p['tutor_nome']})" for p in pets if p["id"] == pid
                ),
            )
            servico_id = st.selectbox(
                "Serviço",
                options=servico_ids,
                index=servico_index,
                format_func=lambda sid: next(
                    f"{s['nome']} ({formatar_moeda(s['preco_padrao'])})"
                    for s in servicos
                    if s["id"] == sid
                ),
            )
            c1, c2, c3 = st.columns(3)
            dia = c1.date_input("Data de início", value=data_valor, format="DD/MM/YYYY")
            hora = c2.time_input("Horário", value=hora_valor)
            status = c3.selectbox("Status", STATUS_AGENDAMENTO, index=status_index)
            profissional = st.text_input(
                "Profissional",
                value=editando["profissional"] if editando else "",
            )
            valor_default = (
                float(editando["valor_cobrado"])
                if editando and editando["valor_cobrado"] is not None
                else valores_servico[servico_id]
            )
            valor = st.number_input("Valor cobrado", min_value=0.0, value=valor_default, step=5.0)

            # Controle de Pagamento
            pago_default = bool(editando["pago"]) if editando and editando.get("pago") else False
            servico_pago = st.checkbox("Serviço Pago?", value=pago_default)
            data_pagamento_input = None
            if servico_pago:
                dt_pag_default = dia
                if editando and editando.get("data_pagamento"):
                    try:
                        dt_pag_default = datetime.strptime(editando["data_pagamento"][:10], "%Y-%m-%d").date()
                    except ValueError:
                        pass
                data_pagamento_input = st.date_input("Data do pagamento", value=dt_pag_default, format="DD/MM/YYYY")

            # Opções de Recorrência
            st.markdown("---")
            repetir = st.checkbox("Repetir Evento", value=config_rrule["repetir"])
            rrule_str = None

            if repetir:
                col_freq, col_dias = st.columns((1, 2))
                opcoes_freq = ("Diário", "Semanal", "Quinzenal", "Mensal")
                freq_idx = (
                    opcoes_freq.index(config_rrule["frequencia"])
                    if config_rrule["frequencia"] in opcoes_freq
                    else 0
                )
                frequencia = col_freq.selectbox("Frequência", opcoes_freq, index=freq_idx)

                dias_selecionados_idx = []
                if frequencia in ("Semanal", "Quinzenal"):
                    dias_iniciais = (
                        config_rrule["dias_semana"]
                        if config_rrule["dias_semana"]
                        else [dia.weekday()]
                    )
                    dias_selecionados_nomes = col_dias.multiselect(
                        "Dias da semana",
                        options=list(DIAS_SEMANA),
                        default=[DIAS_SEMANA[idx] for idx in dias_iniciais if idx < len(DIAS_SEMANA)],
                    )
                    dias_selecionados_idx = [
                        DIAS_SEMANA.index(nome) for nome in dias_selecionados_nomes
                    ]

                rrule_str = construir_rrule(frequencia, dias_selecionados_idx)

            observacoes = st.text_area(
                "Observações de manejo / produtos aplicados",
                value=editando["observacoes"] if editando else "",
            )
            col_a, col_b, col_c = st.columns(3)
            salvar = col_a.button("Salvar", type="primary", key="btn_salvar_agendamento")
            cancelar = col_b.button("Cancelar edição", key="btn_cancelar_agendamento") if editando else False
            excluir = col_c.button("Excluir série", key="btn_excluir_agendamento") if editando else False

        if cancelar:
            st.session_state.agendamento_edit_id = None
            st.rerun()
        if excluir and editando:
            excluir_agendamento(editando["id"])
            st.session_state.agendamento_edit_id = None
            st.rerun()
        if salvar:
            salvar_agendamento(
                pet_id=pet_id,
                servico_id=servico_id,
                data_hora=datetime.combine(dia, hora),
                status=status,
                profissional=profissional,
                valor_cobrado=valor,
                observacoes=observacoes,
                rrule=rrule_str,
                exdate=editando["exdate"] if editando else None,
                pago=1 if servico_pago else 0,
                data_pagamento=data_pagamento_input if servico_pago else None,
                agendamento_id=editando["id"] if editando else None,
            )
            st.session_state.agendamento_edit_id = None
            st.success("Agendamento salvo.")
            st.rerun()


def render_mes(dia: date) -> None:
    c_prev, c_title, c_next = st.columns((1, 3, 1))
    if c_prev.button("◀ Mês anterior"):
        anterior = (date(dia.year, dia.month, 1) - timedelta(days=1)).replace(day=1)
        ir_para("mes", anterior)
    c_title.markdown(f"### {rotulo_mes(dia)}")
    if c_next.button("Mês seguinte ▶"):
        if dia.month == 12:
            proximo = date(dia.year + 1, 1, 1)
        else:
            proximo = date(dia.year, dia.month + 1, 1)
        ir_para("mes", proximo)

    totais = totais_por_dia(dia.year, dia.month)
    cab = st.columns(7)
    for i, nome in enumerate(DIAS_SEMANA):
        cab[i].markdown(f"**{nome[:3]}**")

    grade = calendar.monthcalendar(dia.year, dia.month)
    for semana in grade:
        cols = st.columns(7)
        for i, numero in enumerate(semana):
            with cols[i]:
                if numero == 0:
                    st.write("")
                    continue
                atual = date(dia.year, dia.month, numero)
                info = totais.get(atual.isoformat(), {"qtd": 0, "valor": 0.0})
                rotulo = f"{numero:02d}\n{info['qtd']} ag."
                if st.button(rotulo, key=f"dia_{atual.isoformat()}", use_container_width=True):
                    ir_para("dia", atual)
                st.caption(formatar_moeda(info["valor"]) if info["qtd"] else "—")
    if st.button("Abrir semana desta data"):
        ir_para("semana", dia)


def render_semana(dia: date) -> None:
    inicio = inicio_semana(dia)
    fim = fim_semana(dia)
    c_prev, c_title, c_next = st.columns((1, 3, 1))
    if c_prev.button("◀ Semana anterior"):
        ir_para("semana", inicio - timedelta(days=7))
    c_title.markdown(
        f"### Semana {inicio.strftime('%d/%m')} — {fim.strftime('%d/%m/%Y')}"
    )
    if c_next.button("Semana seguinte ▶"):
        ir_para("semana", inicio + timedelta(days=7))

    itens = listar_agendamentos(inicio, fim)
    ativos = [a for a in itens if a["status"] != "Cancelado"]
    st.metric("Faturamento estimado da semana", formatar_moeda(sum(a["valor_estimado"] for a in ativos)))

    por_dia: dict[date, list] = {inicio + timedelta(days=i): [] for i in range(7)}
    for item in itens:
        chave = date.fromisoformat(item["data_hora"][:10])
        if chave in por_dia:
            por_dia[chave].append(item)

    cols = st.columns(7)
    for i, (dia_col, lista) in enumerate(por_dia.items()):
        with cols[i]:
            st.markdown(f"**{DIAS_SEMANA[i][:3]} {dia_col.strftime('%d/%m')}**")
            if st.button("Zoom", key=f"zoom_{dia_col.isoformat()}", use_container_width=True):
                ir_para("dia", dia_col)
            receita = sum(a["valor_estimado"] for a in lista if a["status"] != "Cancelado")
            st.caption(formatar_moeda(receita))
            if not lista:
                st.write("—")
            for item in lista:
                hora = item["data_hora"][11:16]
                badge_recorrente = " 🔁" if item.get("rrule") else ""
                st.markdown(
                    f"{hora}{badge_recorrente} **{item['pet_nome']}**<br>"
                    f"<small>{item['servico_nome']} · {item['status']}</small>",
                    unsafe_allow_html=True,
                )
    formulario_agendamento(dia)


def render_dia(dia: date) -> None:
    c_prev, c_title, c_next = st.columns((1, 3, 1))
    if c_prev.button("◀ Dia anterior"):
        ir_para("dia", dia - timedelta(days=1))
    c_title.markdown(f"### {DIAS_SEMANA[dia.weekday()]}, {dia.strftime('%d/%m/%Y')}")
    if c_next.button("Dia seguinte ▶"):
        ir_para("dia", dia + timedelta(days=1))

    aniversariantes = aniversariantes_do_dia(dia)
    with st.container(border=True):
        st.subheader("Pets aniversariantes do dia")
        if not aniversariantes:
            st.caption("Nenhum aniversariante nesta data.")
        for pet in aniversariantes:
            mensagem = (
                f"Olá {pet['tutor_nome']}! Feliz aniversário para o(a) {pet['nome']}! "
                "A equipe do pet shop manda um carinho especial hoje."
            )
            link = link_whatsapp(pet["tutor_telefone"], mensagem)
            col_txt, col_btn = st.columns((3, 1))
            col_txt.markdown(f"**{pet['nome']}** · tutor {pet['tutor_nome']}")
            if link:
                col_btn.link_button("Parabéns no WhatsApp", link)
            else:
                col_btn.caption("Sem telefone")

    itens = listar_agendamentos(dia, dia)
    st.subheader("Serviços do dia")
    if not itens:
        st.info("Nenhum agendamento neste dia.")
    for idx, item in enumerate(itens):
        with st.container(border=True):
            top, acoes = st.columns((3.5, 1.5))
            rotulo_recorrente = " 🔁 (Recorrente)" if item.get("rrule") else ""
            if item.get("pago"):
                dt_pag_str = item.get("data_pagamento")
                if dt_pag_str:
                    try:
                        dt_fmt = datetime.strptime(dt_pag_str[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
                        indicador_pago = f"🟢 Pago ({dt_fmt})"
                    except ValueError:
                        indicador_pago = "🟢 Pago"
                else:
                    indicador_pago = "🟢 Pago"
            else:
                indicador_pago = "🔴 A Receber"

            top.markdown(
                f"**{item['data_hora'][11:16]}** · {item['pet_nome']} "
                f"({item['tutor_nome']}) · {item['servico_nome']}{rotulo_recorrente}"
            )
            top.caption(
                f"Profissional: {item['profissional'] or '-'} · "
                f"Status: {item['status']} · {formatar_moeda(item['valor_estimado'])} · {indicador_pago}"
            )
            if item["alergias_restricoes"] or item["temperamento"]:
                top.caption(
                    f"Manejo: {item['temperamento'] or '-'} · "
                    f"Alergias: {item['alergias_restricoes'] or '-'}"
                )
            if item["observacoes"]:
                top.write(item["observacoes"])

            key_suffix = f"{item['id']}_{idx}_{item['data_hora'][:10]}"
            if acoes.button("Editar Série", key=f"ed_ag_{key_suffix}"):
                st.session_state.agendamento_edit_id = item["id"]
                st.rerun()

            if item.get("rrule"):
                if acoes.button("Remover desta data", key=f"rm_inst_{key_suffix}"):
                    adicionar_excecao_agendamento(item["id"], item["data_hora"])
                    st.rerun()

            if item.get("pago"):
                if acoes.button("Marcar A Receber", key=f"pag_off_{key_suffix}"):
                    atualizar_pago_agendamento(item["id"], pago=0)
                    st.rerun()
            else:
                if acoes.button("Marcar Pago", key=f"pag_on_{key_suffix}"):
                    data_pag_padrao = item["data_hora"][:10]
                    atualizar_pago_agendamento(item["id"], pago=1, data_pagamento=data_pag_padrao)
                    st.rerun()

            novo_status = acoes.selectbox(
                "Status",
                STATUS_AGENDAMENTO,
                index=STATUS_AGENDAMENTO.index(item["status"]),
                key=f"st_ag_{key_suffix}",
                label_visibility="collapsed",
            )
            if novo_status != item["status"]:
                atualizar_status_agendamento(item["id"], novo_status)
                st.rerun()

    formulario_agendamento(dia)


if nivel == "mes":
    render_mes(referencia)
elif nivel == "semana":
    render_semana(referencia)
else:
    render_dia(referencia)
