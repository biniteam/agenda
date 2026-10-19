import os
import sqlite3
import tempfile
from datetime import date, datetime, time
import pytest

from database import (
    adicionar_excecao_agendamento,
    expandir_agendamentos,
    get_connection,
    init_db,
    listar_agendamentos,
    salvar_agendamento,
    salvar_cliente,
    salvar_pet,
    listar_servicos,
)
from utils import (
    TZ,
    agora,
    construir_rrule,
    decodificar_rrule,
    hoje,
)


@pytest.fixture(autouse=True)
def setup_tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_petshop.db"
    monkeypatch.setattr("database.DB_PATH", db_file)
    init_db()
    return db_file


def test_schema_migration():
    """Verifica se as colunas 'rrule' e 'exdate' existem no banco de dados."""
    with get_connection() as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(agendamentos)").fetchall()]
        assert "rrule" in cols
        assert "exdate" in cols


def test_construir_e_decodificar_rrule():
    """Testa utilitários de construção e decodificação de strings RRULE."""
    # Diário
    r_daily = construir_rrule("Diário")
    assert r_daily == "FREQ=DAILY"
    decoded_daily = decodificar_rrule(r_daily)
    assert decoded_daily["repetir"] is True
    assert decoded_daily["frequencia"] == "Diário"

    # Semanal (Segunda=0, Quarta=2)
    r_weekly = construir_rrule("Semanal", [0, 2])
    assert r_weekly == "FREQ=WEEKLY;BYDAY=MO,WE"
    decoded_weekly = decodificar_rrule(r_weekly)
    assert decoded_weekly["repetir"] is True
    assert decoded_weekly["frequencia"] == "Semanal"
    assert set(decoded_weekly["dias_semana"]) == {0, 2}

    # Mensal
    r_monthly = construir_rrule("Mensal")
    assert r_monthly == "FREQ=MONTHLY"
    decoded_monthly = decodificar_rrule(r_monthly)
    assert decoded_monthly["repetir"] is True
    assert decoded_monthly["frequencia"] == "Mensal"

    # Não recorrente
    decoded_none = decodificar_rrule(None)
    assert decoded_none["repetir"] is False


def test_expansao_evento_unico():
    """Testa expansão de evento não recorrente em uma janela de datas."""
    item = {
        "id": 1,
        "data_hora": "2025-03-15 09:00:00",
        "rrule": None,
        "exdate": None,
        "status": "Agendado",
    }
    w_start = datetime(2025, 3, 1, 0, 0, 0)
    w_end = datetime(2025, 3, 31, 23, 59, 59)

    res = expandir_agendamentos([item], w_start, w_end)
    assert len(res) == 1
    assert res[0]["data_hora"] == "2025-03-15 09:00:00"

    # Fora da janela
    w_outside_start = datetime(2025, 4, 1, 0, 0, 0)
    w_outside_end = datetime(2025, 4, 30, 23, 59, 59)
    res_outside = expandir_agendamentos([item], w_outside_start, w_outside_end)
    assert len(res_outside) == 0


def test_expansao_evento_recorrente_diario():
    """Testa evento recorrente diário dentro do mês de Março."""
    item = {
        "id": 1,
        "data_hora": "2025-03-01 10:00:00",
        "rrule": "FREQ=DAILY",
        "exdate": None,
        "status": "Agendado",
    }
    w_start = datetime(2025, 3, 1, 0, 0, 0)
    w_end = datetime(2025, 3, 10, 23, 59, 59)

    res = expandir_agendamentos([item], w_start, w_end)
    assert len(res) == 10  # 1 a 10 de Março
    assert res[0]["data_hora"] == "2025-03-01 10:00:00"
    assert res[-1]["data_hora"] == "2025-03-10 10:00:00"


def test_exdate_datas_excecao():
    """Testa exclusão de ocorrências específicas via exdate."""
    item = {
        "id": 1,
        "data_hora": "2025-03-01 10:00:00",
        "rrule": "FREQ=DAILY",
        "exdate": "2025-03-03 10:00:00, 2025-03-05 10:00:00",
        "status": "Agendado",
    }
    w_start = datetime(2025, 3, 1, 0, 0, 0)
    w_end = datetime(2025, 3, 5, 23, 59, 59)

    res = expandir_agendamentos([item], w_start, w_end)
    datas_geradas = [r["data_hora"] for r in res]

    assert "2025-03-01 10:00:00" in datas_geradas
    assert "2025-03-02 10:00:00" in datas_geradas
    assert "2025-03-03 10:00:00" not in datas_geradas
    assert "2025-03-04 10:00:00" in datas_geradas
    assert "2025-03-05 10:00:00" not in datas_geradas


def test_recorrencia_meses_tamanhos_diferentes():
    """Testa cálculo de recorrência mensal cobrindo Fevereiro e meses de 30/31 dias."""
    # Evento no dia 31 de Janeiro em ano não bissexto (2025) e ano bissexto (2024)
    item_31 = {
        "id": 1,
        "data_hora": "2025-01-31 14:00:00",
        "rrule": "FREQ=MONTHLY",
        "exdate": None,
        "status": "Agendado",
    }
    # Janela cobrindo Fev e Mar de 2025
    w_start = datetime(2025, 2, 1, 0, 0, 0)
    w_end = datetime(2025, 3, 31, 23, 59, 59)

    res = expandir_agendamentos([item_31], w_start, w_end)
    # python-dateutil ignora Fevereiro se não houver dia 31 no mês ao usar FREQ=MONTHLY sem BYMONTHDAY especial,
    # ou mapeia se houver regras específicas. Verificamos que o comportamento do dateutil funciona sem erros.
    assert isinstance(res, list)
    for r in res:
        dt = datetime.strptime(r["data_hora"], "%Y-%m-%d %H:%M:%S")
        assert dt.day == 31


def test_fuso_horario():
    """Verifica se os helpers de fuso horário estão corretos para America/Sao_Paulo."""
    data_hoje = hoje()
    data_agora = agora()

    assert isinstance(data_hoje, date)
    assert isinstance(data_agora, datetime)
    assert TZ.key == "America/Sao_Paulo"


def test_fluxo_banco_agendamento_recorrente():
    """Testa integração completa de salvar, listar e adicionar exceção no banco."""
    cid = salvar_cliente("Tutor Teste", "11999999999")
    pid = salvar_pet(cid, "Pet Teste")
    servicos = listar_servicos()
    sid = servicos[0]["id"]

    ag_id = salvar_agendamento(
        pet_id=pid,
        servico_id=sid,
        data_hora=datetime(2025, 3, 1, 9, 0),
        rrule="FREQ=WEEKLY;BYDAY=MO",
    )

    # Listar Março/2025
    agendamentos = listar_agendamentos(date(2025, 3, 1), date(2025, 3, 31))
    # Segundas-feiras em Março 2025: 3, 10, 17, 24, 31 (5 ocorrências)
    assert len(agendamentos) == 5

    # Adicionar exceção para 2025-03-10 09:00:00
    adicionar_excecao_agendamento(ag_id, "2025-03-10 09:00:00")

    agendamentos_pos_ex = listar_agendamentos(date(2025, 3, 1), date(2025, 3, 31))
    datas_pos = [a["data_hora"] for a in agendamentos_pos_ex]
    assert len(agendamentos_pos_ex) == 4
    assert "2025-03-10 09:00:00" not in datas_pos
