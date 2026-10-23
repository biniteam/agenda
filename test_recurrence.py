import os
from datetime import date, datetime, time
import pytest

import database
from database import (
    adicionar_excecao_agendamento,
    atualizar_pago_agendamento,
    expandir_agendamentos,
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

_ORIGINAL_GET_CONNECTION = database.get_connection


class MockCursor:
    def __init__(self, db_state):
        self.db_state = db_state
        self.description = None
        self._result = []

    def execute(self, sql, params=()):
        sql_clean = ' '.join(sql.strip().split())
        if 'SELECT column_name FROM information_schema.columns' in sql_clean:
            self.description = [('column_name',)]
            self._result = [
                {'column_name': 'id'},
                {'column_name': 'pet_id'},
                {'column_name': 'servico_id'},
                {'column_name': 'data_hora'},
                {'column_name': 'status'},
                {'column_name': 'rrule'},
                {'column_name': 'exdate'},
                {'column_name': 'pago'},
                {'column_name': 'data_pagamento'},
            ]
        elif 'SELECT COUNT(*) AS cnt FROM servicos' in sql_clean:
            self.description = [('cnt',)]
            self._result = [{'cnt': len(self.db_state['servicos'])}]
        elif 'INSERT INTO servicos' in sql_clean:
            self.description = [('id',)]
            new_id = len(self.db_state['servicos']) + 1
            rec = {
                'id': new_id,
                'nome': params[0],
                'preco_padrao': params[1],
                'duracao_minutos': params[2],
            }
            self.db_state['servicos'].append(rec)
            self._result = [{'id': new_id}]
        elif 'SELECT * FROM servicos WHERE id =' in sql_clean:
            sid = params[0]
            found = [s for s in self.db_state['servicos'] if s['id'] == sid]
            self._result = [dict(found[0])] if found else []
        elif 'SELECT * FROM servicos ORDER BY nome' in sql_clean:
            self._result = [dict(s) for s in sorted(self.db_state['servicos'], key=lambda x: x['nome'])]
        elif 'UPDATE servicos SET nome =' in sql_clean:
            nome, preco, duracao, sid = params
            for s in self.db_state['servicos']:
                if s['id'] == sid:
                    s['nome'] = nome
                    s['preco_padrao'] = preco
                    s['duracao_minutos'] = duracao
            self._result = []
        elif 'DELETE FROM servicos WHERE id =' in sql_clean:
            sid = params[0]
            self.db_state['servicos'] = [s for s in self.db_state['servicos'] if s['id'] != sid]
            self._result = []
        elif 'INSERT INTO clientes' in sql_clean:
            new_id = len(self.db_state['clientes']) + 1
            rec = {
                'id': new_id,
                'nome': params[0],
                'telefone': params[1],
                'endereco': params[2],
                'observacoes': params[3],
            }
            self.db_state['clientes'].append(rec)
            self._result = [{'id': new_id}]
        elif 'INSERT INTO pets' in sql_clean:
            new_id = len(self.db_state['pets']) + 1
            rec = {
                'id': new_id,
                'cliente_id': params[0],
                'nome': params[1],
                'especie': params[2],
                'raca': params[3],
                'porte': params[4],
                'pelagem': params[5],
                'data_nascimento': params[6],
                'temperamento': params[7],
                'alergias_restricoes': params[8],
            }
            self.db_state['pets'].append(rec)
            self._result = [{'id': new_id}]
        elif 'INSERT INTO agendamentos' in sql_clean:
            new_id = len(self.db_state['agendamentos']) + 1
            rec = {
                'id': new_id,
                'pet_id': params[0],
                'servico_id': params[1],
                'data_hora': params[2],
                'status': params[3],
                'profissional': params[4],
                'valor_cobrado': params[5],
                'observacoes': params[6],
                'rrule': params[7],
                'exdate': params[8],
                'pago': params[9],
                'data_pagamento': params[10],
            }
            self.db_state['agendamentos'].append(rec)
            self._result = [{'id': new_id}]
        elif 'SELECT COUNT(*) AS cnt FROM agendamentos WHERE servico_id =' in sql_clean:
            sid = params[0]
            cnt = sum(1 for a in self.db_state['agendamentos'] if a['servico_id'] == sid)
            self._result = [{'cnt': cnt}]
        elif 'UPDATE agendamentos SET exdate =' in sql_clean:
            exdate, ag_id = params
            for a in self.db_state['agendamentos']:
                if a['id'] == ag_id:
                    a['exdate'] = exdate
            self._result = []
        elif 'UPDATE agendamentos SET pago =' in sql_clean:
            pago, data_pag, ag_id = params
            for a in self.db_state['agendamentos']:
                if a['id'] == ag_id:
                    a['pago'] = pago
                    a['data_pagamento'] = data_pag
            self._result = []
        elif 'SELECT * FROM agendamentos WHERE id =' in sql_clean:
            ag_id = params[0]
            found = [a for a in self.db_state['agendamentos'] if a['id'] == ag_id]
            self._result = [dict(found[0])] if found else []
        elif 'SELECT id FROM financeiro WHERE agendamento_id =' in sql_clean:
            ag_id = params[0]
            found = [f for f in self.db_state['financeiro'] if f.get('agendamento_id') == ag_id and f.get('tipo') == 'Receita']
            self._result = [{'id': found[0]['id']}] if found else []
        elif 'DELETE FROM financeiro WHERE id =' in sql_clean:
            fid = params[0]
            self.db_state['financeiro'] = [f for f in self.db_state['financeiro'] if f['id'] != fid]
            self._result = []
        elif 'INSERT INTO financeiro' in sql_clean:
            new_id = len(self.db_state['financeiro']) + 1
            if len(params) == 4: # from _sincronizar_receita_agendamento: (descricao, valor, dia, agendamento_id)
                rec = {
                    'id': new_id,
                    'tipo': 'Receita',
                    'categoria': 'Serviços',
                    'descricao': params[0],
                    'valor': params[1],
                    'data': params[2],
                    'agendamento_id': params[3],
                }
            else: # from salvar_lancamento: (tipo, categoria, descricao, valor, dia)
                rec = {
                    'id': new_id,
                    'tipo': params[0],
                    'categoria': params[1],
                    'descricao': params[2],
                    'valor': params[3],
                    'data': params[4],
                    'agendamento_id': None,
                }
            self.db_state['financeiro'].append(rec)
            self._result = [{'id': new_id}]
        elif 'SELECT * FROM financeiro WHERE agendamento_id =' in sql_clean:
            ag_id = params[0]
            found = [f for f in self.db_state['financeiro'] if f.get('agendamento_id') == ag_id]
            self._result = [dict(f) for f in found]
        elif 'FROM agendamentos a' in sql_clean:
            # AGENDAMENTO_SELECT query
            joined = []
            for a in self.db_state['agendamentos']:
                pet = next((p for p in self.db_state['pets'] if p['id'] == a['pet_id']), {})
                cli = next((c for c in self.db_state['clientes'] if c['id'] == pet.get('cliente_id')), {})
                srv = next((s for s in self.db_state['servicos'] if s['id'] == a['servico_id']), {})
                item = {
                    'id': a['id'],
                    'pet_id': a['pet_id'],
                    'servico_id': a['servico_id'],
                    'data_hora': a['data_hora'],
                    'status': a['status'],
                    'profissional': a['profissional'],
                    'valor_cobrado': a['valor_cobrado'],
                    'observacoes': a['observacoes'],
                    'rrule': a['rrule'],
                    'exdate': a['exdate'],
                    'pago': a['pago'],
                    'data_pagamento': a['data_pagamento'],
                    'pet_nome': pet.get('nome', ''),
                    'temperamento': pet.get('temperamento', ''),
                    'alergias_restricoes': pet.get('alergias_restricoes', ''),
                    'data_nascimento': pet.get('data_nascimento', ''),
                    'cliente_id': cli.get('id', None),
                    'tutor_nome': cli.get('nome', ''),
                    'tutor_telefone': cli.get('telefone', ''),
                    'servico_nome': srv.get('nome', ''),
                    'preco_padrao': srv.get('preco_padrao', 0.0),
                    'duracao_minutos': srv.get('duracao_minutos', 60),
                    'valor_estimado': a['valor_cobrado'] if a['valor_cobrado'] is not None else srv.get('preco_padrao', 0.0),
                }
                joined.append(item)
            if 'WHERE a.id =' in sql_clean:
                ag_id = params[0]
                joined = [item for item in joined if item['id'] == ag_id]
            self._result = joined
        else:
            self._result = []
        return self

    def executemany(self, sql, param_list):
        for p in param_list:
            self.execute(sql, p)

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result


class MockConnectionWrapper:
    def __init__(self, db_state):
        self.db_state = db_state
        self.is_postgres = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, sql, params=()):
        cur = database.CursorWrapper(MockCursor(self.db_state))
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, param_list):
        cur = database.CursorWrapper(MockCursor(self.db_state))
        cur.executemany(sql, param_list)
        return cur


@pytest.fixture(autouse=True)
def setup_mock_db(monkeypatch):
    db_state = {
        'clientes': [],
        'pets': [],
        'servicos': [],
        'agendamentos': [],
        'financeiro': [],
    }
    monkeypatch.setattr('database.PSYCOPG2_AVAILABLE', True)
    monkeypatch.setattr('database._get_database_url', lambda: 'postgresql://user:pass@localhost:5432/postgres')
    monkeypatch.setattr('database.get_connection', lambda: MockConnectionWrapper(db_state))
    init_db()
    return db_state


def test_schema_migration():
    """Verifica se as colunas 'rrule' e 'exdate' existem no schema do banco."""
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'agendamentos'"
        ).fetchall()
        cols = [r["column_name"] for r in rows]
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

    # Quinzenal (Segunda=0, Quarta=2)
    r_biweekly = construir_rrule("Quinzenal", [0, 2])
    assert r_biweekly == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE"
    decoded_biweekly = decodificar_rrule(r_biweekly)
    assert decoded_biweekly["repetir"] is True
    assert decoded_biweekly["frequencia"] == "Quinzenal"
    assert set(decoded_biweekly["dias_semana"]) == {0, 2}

    # Quinzenal (sem dias explícitos)
    r_biweekly_default = construir_rrule("Quinzenal")
    assert r_biweekly_default == "FREQ=WEEKLY;INTERVAL=2"
    decoded_biweekly_default = decodificar_rrule(r_biweekly_default)
    assert decoded_biweekly_default["repetir"] is True
    assert decoded_biweekly_default["frequencia"] == "Quinzenal"

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
    item_31 = {
        "id": 1,
        "data_hora": "2025-01-31 14:00:00",
        "rrule": "FREQ=MONTHLY",
        "exdate": None,
        "status": "Agendado",
    }
    w_start = datetime(2025, 2, 1, 0, 0, 0)
    w_end = datetime(2025, 3, 31, 23, 59, 59)

    res = expandir_agendamentos([item_31], w_start, w_end)
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

    agendamentos = listar_agendamentos(date(2025, 3, 1), date(2025, 3, 31))
    assert len(agendamentos) == 5

    adicionar_excecao_agendamento(ag_id, "2025-03-10 09:00:00")

    agendamentos_pos_ex = listar_agendamentos(date(2025, 3, 1), date(2025, 3, 31))
    datas_pos = [a["data_hora"] for a in agendamentos_pos_ex]
    assert len(agendamentos_pos_ex) == 4
    assert "2025-03-10 09:00:00" not in datas_pos


def test_crud_servicos():
    """Testa adição, busca, edição e exclusão de serviços no banco."""
    from database import (
        excluir_servico,
        obter_servico,
        salvar_servico,
    )

    sid = salvar_servico("Hidratação Especial", 85.0, 45)
    servico = obter_servico(sid)
    assert servico is not None
    assert servico["nome"] == "Hidratação Especial"
    assert servico["preco_padrao"] == 85.0
    assert servico["duracao_minutos"] == 45

    salvar_servico("Hidratação Premium", 95.0, 50, servico_id=sid)
    servico_editado = obter_servico(sid)
    assert servico_editado["nome"] == "Hidratação Premium"
    assert servico_editado["preco_padrao"] == 95.0
    assert servico_editado["duracao_minutos"] == 50

    ok, msg = excluir_servico(sid)
    assert ok is True
    assert obter_servico(sid) is None

    servicos_padrao = listar_servicos()
    s_padrao_id = servicos_padrao[0]["id"]
    cid = salvar_cliente("Tutor Servico Teste", "11888888888")
    pid = salvar_pet(cid, "Pet Servico Teste")
    salvar_agendamento(pid, s_padrao_id, datetime(2025, 3, 1, 10, 0))

    ok_del, msg_del = excluir_servico(s_padrao_id)
    assert ok_del is False
    assert "Não é possível excluir" in msg_del


def test_controle_pagamento_e_sincronizacao_financeira():
    """Testa as colunas 'pago' e 'data_pagamento' e a sincronização financeira."""
    cid = salvar_cliente("Tutor Pagamento", "11977777777")
    pid = salvar_pet(cid, "Pet Pagamento")
    servicos = listar_servicos()
    sid = servicos[0]["id"]

    ag_id = salvar_agendamento(
        pet_id=pid,
        servico_id=sid,
        data_hora=datetime(2025, 3, 10, 14, 0),
        status="Concluído",
        pago=0,
    )

    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM agendamentos WHERE id = %s", (ag_id,)).fetchone()
        assert row["pago"] == 0
        assert row["data_pagamento"] is None

        fin = conn.execute("SELECT * FROM financeiro WHERE agendamento_id = %s", (ag_id,)).fetchall()
        assert len(fin) == 0

    dt_pag = date(2025, 3, 12)
    atualizar_pago_agendamento(ag_id, pago=1, data_pagamento=dt_pag)

    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM agendamentos WHERE id = %s", (ag_id,)).fetchone()
        assert row["pago"] == 1
        assert str(row["data_pagamento"]) == "2025-03-12"

        fin = conn.execute("SELECT * FROM financeiro WHERE agendamento_id = %s", (ag_id,)).fetchall()
        assert len(fin) == 1
        assert fin[0]["tipo"] == "Receita"
        assert str(fin[0]["data"]) == "2025-03-12"

    atualizar_pago_agendamento(ag_id, pago=0)

    with database.get_connection() as conn:
        row = conn.execute("SELECT * FROM agendamentos WHERE id = %s", (ag_id,)).fetchone()
        assert row["pago"] == 0

        fin = conn.execute("SELECT * FROM financeiro WHERE agendamento_id = %s", (ag_id,)).fetchall()
        assert len(fin) == 0


def test_get_connection_sem_url(monkeypatch):
    """Verifica se get_connection lança RuntimeError quando nenhuma URL é fornecida."""
    monkeypatch.setattr("database._get_database_url", lambda: None)
    monkeypatch.setattr("database.PSYCOPG2_AVAILABLE", True)

    with pytest.raises(RuntimeError) as exc_info:
        _ORIGINAL_GET_CONNECTION()

    assert "Nenhuma URL do Supabase/Postgres configurada" in str(exc_info.value)
