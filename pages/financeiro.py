from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from database import (
    excluir_lancamento,
    faturamento_mensal,
    faturamento_por_servico,
    faturamento_semanal,
    init_db,
    listar_lancamentos,
    media_faturamento_dias_uteis,
    resumo_financeiro,
    salvar_lancamento,
    ticket_medio,
)
from utils import (
    CATEGORIAS_DESPESA,
    CATEGORIAS_RECEITA,
    MESES,
    formatar_moeda,
    fim_semana,
    hoje,
    inicio_semana,
)

init_db()

st.title("Financeiro")

referencia = hoje()
inicio_mes = referencia.replace(day=1)
if referencia.month == 12:
    fim_mes = date(referencia.year, 12, 31)
else:
    fim_mes = date(referencia.year, referencia.month + 1, 1) - timedelta(days=1)

periodo = st.date_input(
    "Período dos gráficos",
    value=(inicio_mes, fim_mes),
    format="DD/MM/YYYY",
)
if isinstance(periodo, tuple) and len(periodo) == 2:
    inicio_periodo, fim_periodo = periodo
else:
    inicio_periodo, fim_periodo = inicio_mes, fim_mes

resumo_dia = resumo_financeiro(referencia, referencia)
resumo_semana = resumo_financeiro(inicio_semana(referencia), fim_semana(referencia))
media_util = media_faturamento_dias_uteis(inicio_periodo, fim_periodo)
ticket = ticket_medio(inicio_periodo, fim_periodo)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Lucro líquido diário", formatar_moeda(resumo_dia["lucro"]))
m2.metric("Lucro líquido semanal", formatar_moeda(resumo_semana["lucro"]))
m3.metric("Média de faturamento (dias úteis)", formatar_moeda(media_util))
m4.metric("Ticket médio por atendimento", formatar_moeda(ticket))

st.caption(
    f"Receitas do dia {formatar_moeda(resumo_dia['receitas'])} · "
    f"Despesas do dia {formatar_moeda(resumo_dia['despesas'])}"
)

semanas = faturamento_semanal(inicio_periodo, fim_periodo)
df_semanas = pd.DataFrame(semanas)
if df_semanas.empty:
    df_semanas = pd.DataFrame({"semana": [], "total": []})
df_semanas["rotulo"] = df_semanas["semana"].apply(
    lambda s: date.fromisoformat(s).strftime("%d/%m") if s else ""
)

mensal = faturamento_mensal(referencia.year)
df_mensal = pd.DataFrame(mensal)
df_mensal["rotulo"] = df_mensal["mes"].apply(lambda m: MESES[int(m.split("-")[1]) - 1][:3])

por_servico = faturamento_por_servico(inicio_periodo, fim_periodo)
df_servico = pd.DataFrame(por_servico)

g1, g2 = st.columns(2)
with g1:
    fig_semana = px.bar(
        df_semanas,
        x="rotulo",
        y="total",
        title="Evolução do faturamento semanal",
        labels={"rotulo": "Semana (início)", "total": "R$"},
    )
    fig_semana.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_semana, use_container_width=True)
with g2:
    fig_mes = px.line(
        df_mensal,
        x="rotulo",
        y="total",
        markers=True,
        title=f"Faturamento mensal {referencia.year}",
        labels={"rotulo": "Mês", "total": "R$"},
    )
    fig_mes.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_mes, use_container_width=True)

if df_servico.empty:
    st.info("Conclua atendimentos no período para ver a distribuição por serviço.")
else:
    fig_servico = px.pie(
        df_servico,
        names="servico",
        values="total",
        title="Distribuição de faturamento por tipo de serviço",
    )
    fig_servico.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_servico, use_container_width=True)

st.subheader("Lançamentos")
col_form, col_lista = st.columns((1, 1.4))

with col_form:
    with st.form("form_lancamento"):
        tipo = st.radio("Tipo", ("Receita", "Despesa"), horizontal=True)
        categorias = CATEGORIAS_RECEITA if tipo == "Receita" else CATEGORIAS_DESPESA
        categoria = st.selectbox("Categoria", categorias)
        descricao = st.text_input("Descrição")
        valor = st.number_input("Valor", min_value=0.0, step=10.0)
        data_lanc = st.date_input("Data", value=referencia, format="DD/MM/YYYY")
        if st.form_submit_button("Lançar", type="primary"):
            if valor <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                salvar_lancamento(tipo, categoria, descricao, valor, data_lanc)
                st.success("Lançamento registrado.")
                st.rerun()

with col_lista:
    lancamentos = listar_lancamentos(inicio_periodo, fim_periodo)
    if not lancamentos:
        st.info("Nenhum lançamento neste período.")
    for item in lancamentos:
        origem = "serviço concluído" if item["agendamento_id"] else "manual"
        with st.container(border=True):
            c1, c2 = st.columns((4, 1))
            sinal = "+" if item["tipo"] == "Receita" else "−"
            c1.markdown(
                f"**{sinal} {formatar_moeda(item['valor'])}** · {item['tipo']} · "
                f"{item['categoria'] or '-'}"
            )
            c1.caption(f"{item['data']} · {item['descricao'] or origem}")
            if not item["agendamento_id"]:
                if c2.button("Excluir", key=f"del_fin_{item['id']}"):
                    excluir_lancamento(item["id"])
                    st.rerun()
            else:
                c2.caption("auto")
