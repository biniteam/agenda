"""Conexão PostgreSQL / Supabase, schema e consultas do pet shop."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from dateutil.rrule import rrulestr, rruleset

try:
    import streamlit as st
except ImportError:
    st = None

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False

ROOT_DIR = Path(__file__).resolve().parent

SERVICOS_PADRAO = (
    ("Banho", 50.0, 60),
    ("Tosa", 70.0, 90),
    ("Banho e Tosa", 110.0, 120),
)

AGENDAMENTO_SELECT = """
    SELECT
        a.id,
        a.pet_id,
        a.servico_id,
        a.data_hora,
        a.status,
        a.profissional,
        a.valor_cobrado,
        a.observacoes,
        a.rrule,
        a.exdate,
        a.pago,
        a.data_pagamento,
        p.nome AS pet_nome,
        p.temperamento,
        p.alergias_restricoes,
        p.data_nascimento,
        c.id AS cliente_id,
        c.nome AS tutor_nome,
        c.telefone AS tutor_telefone,
        s.nome AS servico_nome,
        s.preco_padrao,
        s.duracao_minutos,
        COALESCE(a.valor_cobrado, s.preco_padrao, 0) AS valor_estimado
    FROM agendamentos a
    JOIN pets p ON p.id = a.pet_id
    JOIN clientes c ON c.id = p.cliente_id
    JOIN servicos s ON s.id = a.servico_id
"""


def _get_database_url() -> str | None:
    # 1. Tentar st.secrets["supabase"]
    if st is not None:
        try:
            supabase_secrets = st.secrets.get("supabase")
            if isinstance(supabase_secrets, dict):
                url = supabase_secrets.get("db_url") or supabase_secrets.get("url") or supabase_secrets.get("connection_string")
                if url:
                    return str(url)
            elif isinstance(supabase_secrets, str):
                return supabase_secrets

            url_secret = st.secrets.get("DATABASE_URL") or st.secrets.get("SUPABASE_DB_URL")
            if url_secret:
                return str(url_secret)
        except Exception:
            pass

    # 2. Tentar variáveis de ambiente
    for env_var in ("SUPABASE_DB_URL", "DATABASE_URL", "POSTGRES_URL"):
        if os.getenv(env_var):
            return os.getenv(env_var)

    # 3. Construir URL a partir de variáveis de ambiente separadas do Supabase/Postgres
    user = os.getenv("PGUSER") or os.getenv("SUPABASE_USER")
    password = os.getenv("PGPASSWORD") or os.getenv("SUPABASE_PASSWORD")
    host = os.getenv("PGHOST") or os.getenv("SUPABASE_HOST")
    port = os.getenv("PGPORT") or os.getenv("SUPABASE_PORT") or "5432"
    dbname = os.getenv("PGDATABASE") or os.getenv("SUPABASE_DB") or "postgres"

    if user and password and host:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    return None


class CursorWrapper:
    """Wrapper para tratar consultas com cursor de psycopg2."""

    def __init__(self, cursor: Any):
        self.cursor = cursor

    def execute(self, sql: str, params: tuple | list | dict = ()) -> CursorWrapper:
        self.cursor.execute(sql, params)
        return self

    def executemany(self, sql: str, param_list: list) -> CursorWrapper:
        self.cursor.executemany(sql, param_list)
        return self

    def fetchone(self) -> dict[str, Any] | None:
        row = self.cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        if hasattr(row, "keys"):
            return dict(row)
        if isinstance(row, (list, tuple)):
            if self.cursor.description:
                cols = [desc[0] for desc in self.cursor.description]
                return dict(zip(cols, row))
        return row

    def fetchall(self) -> list[dict[str, Any]]:
        rows = self.cursor.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return list(rows)
        if hasattr(rows[0], "keys"):
            return [dict(r) for r in rows[0:]]
        if self.cursor.description:
            cols = [desc[0] for desc in self.cursor.description]
            return [dict(zip(cols, r)) for r in rows]
        return rows


class ConnectionWrapper:
    """Wrapper de conexão PostgreSQL com autocommit/commit context management."""

    def __init__(self, conn: Any):
        self.conn = conn
        self.is_postgres = True

    def __enter__(self) -> ConnectionWrapper:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()

    def cursor(self) -> CursorWrapper:
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return CursorWrapper(cur)

    def execute(self, sql: str, params: tuple | list | dict = ()) -> CursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql: str, param_list: list) -> CursorWrapper:
        cur = self.cursor()
        cur.executemany(sql, param_list)
        return cur

    def executescript(self, script: str) -> None:
        cur = self.conn.cursor()
        cur.execute(script)


def get_connection() -> ConnectionWrapper:
    if not PSYCOPG2_AVAILABLE:
        msg = "psycopg2 não está disponível. Certifique-se de ter psycopg2-binary instalado."
        print(f"[DATABASE ERROR] {msg}")
        raise RuntimeError(msg)

    db_url = _get_database_url()
    if not db_url:
        msg = "Nenhuma URL do Supabase/Postgres configurada."
        print(f"[DATABASE ERROR] {msg}")
        raise RuntimeError(msg)

    try:
        print("[DATABASE LOG] Conectando ao Supabase/Postgres...")
        conn = psycopg2.connect(db_url)
        print("[DATABASE LOG] Conexão com Supabase/Postgres estabelecida com sucesso!")
        if st is not None:
            try:
                st.info("[DATABASE LOG] Conectado ao Supabase/Postgres com sucesso.")
            except Exception:
                pass
        return ConnectionWrapper(conn)
    except Exception as e:
        msg = f"Falha ao conectar ao Supabase/Postgres: {e}"
        print(f"[DATABASE ERROR] {msg}")
        if st is not None:
            try:
                st.error(msg)
            except Exception:
                pass
        raise RuntimeError(msg) from e


def init_db() -> None:
    print("[DATABASE LOG] Iniciando inicialização do banco de dados (init_db)...")
    if st is not None:
        try:
            st.info("[DATABASE LOG] Iniciando inicialização do banco de dados (init_db)...")
        except Exception:
            pass

    try:
        with get_connection() as conn:
            print("[DATABASE LOG] Criando schema no banco de dados PostgreSQL (Supabase)...")

            comandos = [
                ("clientes", """
                CREATE TABLE IF NOT EXISTS clientes (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    telefone TEXT,
                    endereco TEXT,
                    observacoes TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """),
                ("pets", """
                CREATE TABLE IF NOT EXISTS pets (
                    id SERIAL PRIMARY KEY,
                    cliente_id INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    especie TEXT,
                    raca TEXT,
                    porte TEXT,
                    pelagem TEXT,
                    data_nascimento TEXT,
                    temperamento TEXT,
                    alergias_restricoes TEXT,
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                );
                """),
                ("servicos", """
                CREATE TABLE IF NOT EXISTS servicos (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    preco_padrao REAL NOT NULL DEFAULT 0,
                    duracao_minutos INTEGER NOT NULL DEFAULT 60
                );
                """),
                ("agendamentos", """
                CREATE TABLE IF NOT EXISTS agendamentos (
                    id SERIAL PRIMARY KEY,
                    pet_id INTEGER NOT NULL,
                    servico_id INTEGER NOT NULL,
                    data_hora TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Agendado',
                    profissional TEXT,
                    valor_cobrado REAL,
                    observacoes TEXT,
                    rrule TEXT DEFAULT NULL,
                    exdate TEXT DEFAULT NULL,
                    pago INTEGER NOT NULL DEFAULT 0,
                    data_pagamento TEXT DEFAULT NULL,
                    FOREIGN KEY (pet_id) REFERENCES pets(id),
                    FOREIGN KEY (servico_id) REFERENCES servicos(id)
                );
                """),
                ("financeiro", """
                CREATE TABLE IF NOT EXISTS financeiro (
                    id SERIAL PRIMARY KEY,
                    tipo TEXT NOT NULL,
                    categoria TEXT,
                    descricao TEXT,
                    valor REAL NOT NULL,
                    data TEXT NOT NULL,
                    agendamento_id INTEGER,
                    FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
                );
                """),
            ]
            for nome_tabela, cmd in comandos:
                try:
                    print(f"[DATABASE LOG] Executando CREATE TABLE para '{nome_tabela}'...")
                    conn.execute(cmd)
                    print(f"[DATABASE LOG] Tabela '{nome_tabela}' criada ou já existente com sucesso.")
                except Exception as err:
                    error_msg = f"[DATABASE ERROR] Erro ao criar tabela '{nome_tabela}' no Postgres: {err}"
                    print(error_msg)
                    if st is not None:
                        try:
                            st.error(error_msg)
                        except Exception:
                            pass
                    raise err

            _migrate_db(conn)
            _seed_servicos(conn)
            print("[DATABASE LOG] Inicialização do banco de dados concluída com sucesso!")
            if st is not None:
                try:
                    st.success("[DATABASE LOG] Inicialização do banco de dados concluída com sucesso!")
                except Exception:
                    pass
    except Exception as e:
        final_err_msg = f"[DATABASE ERROR] Falha geral ao inicializar o banco de dados: {e}"
        print(final_err_msg)
        if st is not None:
            try:
                st.error(final_err_msg)
            except Exception:
                pass


def _migrate_db(conn: ConnectionWrapper) -> None:
    print("[DATABASE LOG] Verificando migrations do banco de dados...")
    try:
        conn.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS rrule TEXT DEFAULT NULL")
        conn.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS exdate TEXT DEFAULT NULL")
        conn.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS pago INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS data_pagamento TEXT DEFAULT NULL")
        print("[DATABASE LOG] Migrations concluídas com sucesso.")
    except Exception as err:
        msg = f"[DATABASE ERROR] Erro durante migrations (_migrate_db): {err}"
        print(msg)
        if st is not None:
            try:
                st.error(msg)
            except Exception:
                pass
        raise err


def _seed_servicos(conn: ConnectionWrapper) -> None:
    print("[DATABASE LOG] Verificando população inicial de serviços (_seed_servicos)...")
    try:
        res = conn.execute("SELECT COUNT(*) AS cnt FROM servicos").fetchone()
        count = res["cnt"] if res and "cnt" in res else (list(res.values())[0] if res else 0)
        if count:
            print(f"[DATABASE LOG] Tabela 'servicos' já possui {count} registros. Seed ignorado.")
            return
        conn.executemany(
            "INSERT INTO servicos (nome, preco_padrao, duracao_minutos) VALUES (%s, %s, %s)",
            SERVICOS_PADRAO,
        )
        print("[DATABASE LOG] Serviços padrão inseridos com sucesso.")
    except Exception as err:
        msg = f"[DATABASE ERROR] Erro durante população inicial (_seed_servicos): {err}"
        print(msg)
        if st is not None:
            try:
                st.error(msg)
            except Exception:
                pass
        raise err


def _as_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def _as_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _iso_date(valor: date | datetime | str) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def _iso_datetime(valor: datetime | str) -> str:
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor)


# --- Clientes ---


def listar_clientes() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.*, COUNT(p.id) AS qtd_pets
            FROM clientes c
            LEFT JOIN pets p ON p.cliente_id = c.id
            GROUP BY c.id
            ORDER BY c.nome
            """
        ).fetchall()
    return _as_dicts(rows)


def obter_cliente(cliente_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM clientes WHERE id = %s", (cliente_id,)).fetchone()
    return _as_dict(row)


def salvar_cliente(
    nome: str,
    telefone: str = "",
    endereco: str = "",
    observacoes: str = "",
    cliente_id: int | None = None,
) -> int:
    with get_connection() as conn:
        if cliente_id:
            conn.execute(
                """
                UPDATE clientes
                SET nome = %s, telefone = %s, endereco = %s, observacoes = %s
                WHERE id = %s
                """,
                (nome.strip(), telefone.strip(), endereco.strip(), observacoes.strip(), cliente_id),
            )
            return cliente_id

        cur = conn.execute(
            """
            INSERT INTO clientes (nome, telefone, endereco, observacoes)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (nome.strip(), telefone.strip(), endereco.strip(), observacoes.strip()),
        )
        res = cur.fetchone()
        return int(res["id"])


def excluir_cliente(cliente_id: int) -> None:
    with get_connection() as conn:
        pets = conn.execute(
            "SELECT id FROM pets WHERE cliente_id = %s", (cliente_id,)
        ).fetchall()
        pet_ids = [row["id"] for row in pets]
        if pet_ids:
            placeholders = ",".join("%s" for _ in pet_ids)
            conn.execute(
                f"DELETE FROM financeiro WHERE agendamento_id IN "
                f"(SELECT id FROM agendamentos WHERE pet_id IN ({placeholders}))",
                pet_ids,
            )
            conn.execute(
                f"DELETE FROM agendamentos WHERE pet_id IN ({placeholders})",
                pet_ids,
            )
            conn.execute("DELETE FROM pets WHERE cliente_id = %s", (cliente_id,))
        conn.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))


# --- Pets ---


def listar_pets(cliente_id: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT p.*, c.nome AS tutor_nome, c.telefone AS tutor_telefone
        FROM pets p
        JOIN clientes c ON c.id = p.cliente_id
    """
    params: list[Any] = []
    if cliente_id is not None:
        sql += " WHERE p.cliente_id = %s"
        params.append(cliente_id)
    sql += " ORDER BY c.nome, p.nome"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _as_dicts(rows)


def obter_pet(pet_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.*, c.nome AS tutor_nome, c.telefone AS tutor_telefone
            FROM pets p
            JOIN clientes c ON c.id = p.cliente_id
            WHERE p.id = %s
            """,
            (pet_id,),
        ).fetchone()
    return _as_dict(row)


def salvar_pet(
    cliente_id: int,
    nome: str,
    especie: str = "",
    raca: str = "",
    porte: str = "M",
    pelagem: str = "",
    data_nascimento: str | date | None = None,
    temperamento: str = "",
    alergias_restricoes: str = "",
    pet_id: int | None = None,
) -> int:
    nascimento = _iso_date(data_nascimento) if data_nascimento else None
    with get_connection() as conn:
        if pet_id:
            conn.execute(
                """
                UPDATE pets
                SET cliente_id = %s, nome = %s, especie = %s, raca = %s, porte = %s,
                    pelagem = %s, data_nascimento = %s, temperamento = %s,
                    alergias_restricoes = %s
                WHERE id = %s
                """,
                (
                    cliente_id,
                    nome.strip(),
                    especie.strip(),
                    raca.strip(),
                    porte,
                    pelagem.strip(),
                    nascimento,
                    temperamento.strip(),
                    alergias_restricoes.strip(),
                    pet_id,
                ),
            )
            return pet_id

        cur = conn.execute(
            """
            INSERT INTO pets (
                cliente_id, nome, especie, raca, porte, pelagem,
                data_nascimento, temperamento, alergias_restricoes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                cliente_id,
                nome.strip(),
                especie.strip(),
                raca.strip(),
                porte,
                pelagem.strip(),
                nascimento,
                temperamento.strip(),
                alergias_restricoes.strip(),
            ),
        )
        res = cur.fetchone()
        return int(res["id"])


def excluir_pet(pet_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM financeiro WHERE agendamento_id IN "
            "(SELECT id FROM agendamentos WHERE pet_id = %s)",
            (pet_id,),
        )
        conn.execute("DELETE FROM agendamentos WHERE pet_id = %s", (pet_id,))
        conn.execute("DELETE FROM pets WHERE id = %s", (pet_id,))


def prontuario_pet(pet_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            AGENDAMENTO_SELECT + " WHERE a.pet_id = %s ORDER BY a.data_hora DESC",
            (pet_id,),
        ).fetchall()
    return _as_dicts(rows)


def aniversariantes_do_dia(dia: date) -> list[dict[str, Any]]:
    chave = dia.strftime("%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, c.nome AS tutor_nome, c.telefone AS tutor_telefone
            FROM pets p
            JOIN clientes c ON c.id = p.cliente_id
            WHERE p.data_nascimento IS NOT NULL
              AND p.data_nascimento != ''
              AND TO_CHAR(TO_DATE(p.data_nascimento, 'YYYY-MM-DD'), 'MM-DD') = %s
            ORDER BY p.nome
            """,
            (chave,),
        ).fetchall()
    return _as_dicts(rows)


# --- Serviços ---


def listar_servicos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM servicos ORDER BY nome"
        ).fetchall()
    return _as_dicts(rows)


def obter_servico(servico_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM servicos WHERE id = %s", (servico_id,)
        ).fetchone()
    return _as_dict(row)


def salvar_servico(
    nome: str,
    preco_padrao: float,
    duracao_minutos: int = 60,
    servico_id: int | None = None,
) -> int:
    with get_connection() as conn:
        if servico_id:
            conn.execute(
                """
                UPDATE servicos
                SET nome = %s, preco_padrao = %s, duracao_minutos = %s
                WHERE id = %s
                """,
                (nome.strip(), float(preco_padrao), int(duracao_minutos), servico_id),
            )
            return servico_id

        cur = conn.execute(
            """
            INSERT INTO servicos (nome, preco_padrao, duracao_minutos)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (nome.strip(), float(preco_padrao), int(duracao_minutos)),
        )
        res = cur.fetchone()
        return int(res["id"])


def excluir_servico(servico_id: int) -> tuple[bool, str]:
    with get_connection() as conn:
        res = conn.execute(
            "SELECT COUNT(*) AS cnt FROM agendamentos WHERE servico_id = %s", (servico_id,)
        ).fetchone()
        qtd = res["cnt"] if res and "cnt" in res else (list(res.values())[0] if res else 0)
        if qtd > 0:
            return False, f"Não é possível excluir: existem {qtd} agendamento(s) vinculado(s) a este serviço."
        conn.execute("DELETE FROM servicos WHERE id = %s", (servico_id,))
    return True, "Serviço excluído com sucesso."


# --- Agendamentos e Recorrência ---


def expandir_agendamentos(
    agendamentos: list[dict[str, Any]],
    janela_inicio: datetime,
    janela_fim: datetime,
) -> list[dict[str, Any]]:
    """
    Dada uma lista de agendamentos e uma janela de tempo [janela_inicio, janela_fim],
    expande as ocorrências recorrentes via rrule.between().
    """
    resultados: list[dict[str, Any]] = []

    for item in agendamentos:
        rrule_str = item.get("rrule")
        dtstart = datetime.strptime(str(item["data_hora"])[:19], "%Y-%m-%d %H:%M:%S")

        # Parse exdates
        exdates: set[datetime] = set()
        if item.get("exdate"):
            for ex in item["exdate"].split(","):
                ex_str = ex.strip()
                if ex_str:
                    try:
                        exdates.add(datetime.strptime(ex_str[:19], "%Y-%m-%d %H:%M:%S"))
                    except ValueError:
                        pass

        if not rrule_str:
            # Evento único
            if janela_inicio <= dtstart <= janela_fim and dtstart not in exdates:
                resultados.append(dict(item))
            continue

        # Evento recorrente
        try:
            rule = rrulestr(rrule_str, dtstart=dtstart)
            rs = rruleset()
            rs.rrule(rule)
            for ex in exdates:
                rs.exdate(ex)

            instancias = rs.between(janela_inicio, janela_fim, inc=True)
            for inst in instancias:
                novo_item = dict(item)
                novo_item["data_hora"] = inst.strftime("%Y-%m-%d %H:%M:%S")
                novo_item["e_recorrente"] = True
                resultados.append(novo_item)
        except Exception:
            # Em caso de falha de parsing da rrule, cai para o evento estático
            if janela_inicio <= dtstart <= janela_fim and dtstart not in exdates:
                resultados.append(dict(item))

    # Ordenar resultados por data_hora
    resultados.sort(key=lambda x: str(x["data_hora"]))
    return resultados


def listar_agendamentos(inicio: date, fim: date) -> list[dict[str, Any]]:
    janela_inicio = datetime.combine(inicio, time(0, 0, 0))
    janela_fim = datetime.combine(fim, time(23, 59, 59))

    with get_connection() as conn:
        rows = conn.execute(
            AGENDAMENTO_SELECT + " WHERE a.data_hora <= %s OR a.rrule IS NOT NULL",
            (f"{_iso_date(fim)} 23:59:59",),
        ).fetchall()

    todos = _as_dicts(rows)
    return expandir_agendamentos(todos, janela_inicio, janela_fim)


def totais_por_dia(ano: int, mes: int) -> dict[str, dict[str, Any]]:
    inicio = date(ano, mes, 1)
    if mes == 12:
        fim = date(ano, 12, 31)
    else:
        fim = date(ano, mes + 1, 1) - timedelta(days=1)
    totais: dict[str, dict[str, Any]] = {}
    for item in listar_agendamentos(inicio, fim):
        if item["status"] == "Cancelado":
            continue
        chave = str(item["data_hora"])[:10]
        bucket = totais.setdefault(chave, {"qtd": 0, "valor": 0.0})
        bucket["qtd"] += 1
        bucket["valor"] += float(item["valor_estimado"] or 0)
    return totais


def obter_agendamento(agendamento_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            AGENDAMENTO_SELECT + " WHERE a.id = %s", (agendamento_id,)
        ).fetchone()
    return _as_dict(row)


def salvar_agendamento(
    pet_id: int,
    servico_id: int,
    data_hora: datetime | str,
    status: str = "Agendado",
    profissional: str = "",
    valor_cobrado: float | None = None,
    observacoes: str = "",
    rrule: str | None = None,
    exdate: str | None = None,
    pago: int = 0,
    data_pagamento: date | str | None = None,
    agendamento_id: int | None = None,
) -> int:
    instante = _iso_datetime(data_hora)
    rrule_val = rrule.strip() if rrule and rrule.strip() else None
    exdate_val = exdate.strip() if exdate and exdate.strip() else None
    pago_val = int(pago)
    data_pagamento_val = _iso_date(data_pagamento) if data_pagamento else None

    with get_connection() as conn:
        if agendamento_id:
            conn.execute(
                """
                UPDATE agendamentos
                SET pet_id = %s, servico_id = %s, data_hora = %s, status = %s,
                    profissional = %s, valor_cobrado = %s, observacoes = %s,
                    rrule = %s, exdate = %s, pago = %s, data_pagamento = %s
                WHERE id = %s
                """,
                (
                    pet_id,
                    servico_id,
                    instante,
                    status,
                    profissional.strip(),
                    valor_cobrado,
                    observacoes.strip(),
                    rrule_val,
                    exdate_val,
                    pago_val,
                    data_pagamento_val,
                    agendamento_id,
                ),
            )
            novo_id = agendamento_id
        else:
            cur = conn.execute(
                """
                INSERT INTO agendamentos (
                    pet_id, servico_id, data_hora, status, profissional,
                    valor_cobrado, observacoes, rrule, exdate, pago, data_pagamento
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    pet_id,
                    servico_id,
                    instante,
                    status,
                    profissional.strip(),
                    valor_cobrado,
                    observacoes.strip(),
                    rrule_val,
                    exdate_val,
                    pago_val,
                    data_pagamento_val,
                ),
            )
            res = cur.fetchone()
            novo_id = int(res["id"])

    _sincronizar_receita_agendamento(novo_id)
    return novo_id


def adicionar_excecao_agendamento(agendamento_id: int, data_hora_excecao: str | datetime) -> None:
    agendamento = obter_agendamento(agendamento_id)
    if not agendamento:
        return
    instante_str = _iso_datetime(data_hora_excecao)
    exdates_existentes = set()
    if agendamento.get("exdate"):
        for ex in agendamento["exdate"].split(","):
            if ex.strip():
                exdates_existentes.add(ex.strip())
    exdates_existentes.add(instante_str)
    novo_exdate_str = ",".join(sorted(exdates_existentes))

    with get_connection() as conn:
        conn.execute(
            "UPDATE agendamentos SET exdate = %s WHERE id = %s",
            (novo_exdate_str, agendamento_id),
        )


def atualizar_status_agendamento(agendamento_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE agendamentos SET status = %s WHERE id = %s",
            (status, agendamento_id),
        )
    _sincronizar_receita_agendamento(agendamento_id)


def atualizar_pago_agendamento(
    agendamento_id: int,
    pago: int,
    data_pagamento: date | str | None = None,
) -> None:
    pago_val = int(pago)
    data_pag_val = _iso_date(data_pagamento) if data_pagamento else None
    if pago_val == 1 and not data_pag_val:
        ag = obter_agendamento(agendamento_id)
        if ag:
            data_pag_val = ag.get("data_pagamento") or str(ag["data_hora"])[:10]

    with get_connection() as conn:
        conn.execute(
            "UPDATE agendamentos SET pago = %s, data_pagamento = %s WHERE id = %s",
            (pago_val, data_pag_val, agendamento_id),
        )
    _sincronizar_receita_agendamento(agendamento_id)


def excluir_agendamento(agendamento_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM financeiro WHERE agendamento_id = %s", (agendamento_id,)
        )
        conn.execute("DELETE FROM agendamentos WHERE id = %s", (agendamento_id,))


def _sincronizar_receita_agendamento(agendamento_id: int) -> None:
    agendamento = obter_agendamento(agendamento_id)
    if agendamento is None:
        return
    with get_connection() as conn:
        existente = conn.execute(
            "SELECT id FROM financeiro WHERE agendamento_id = %s AND tipo = 'Receita'",
            (agendamento_id,),
        ).fetchone()
        if not agendamento.get("pago"):
            if existente:
                conn.execute("DELETE FROM financeiro WHERE id = %s", (existente["id"],))
            return
        valor = float(agendamento["valor_estimado"] or 0)
        dia = agendamento.get("data_pagamento") or str(agendamento["data_hora"])[:10]
        descricao = (
            f"{agendamento['servico_nome']} — {agendamento['pet_nome']} "
            f"({agendamento['tutor_nome']})"
        )
        if existente:
            conn.execute(
                """
                UPDATE financeiro
                SET categoria = 'Serviços', descricao = %s, valor = %s, data = %s
                WHERE id = %s
                """,
                (descricao, valor, dia, existente["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO financeiro (tipo, categoria, descricao, valor, data, agendamento_id)
                VALUES ('Receita', 'Serviços', %s, %s, %s, %s)
                """,
                (descricao, valor, dia, agendamento_id),
            )


# --- Financeiro ---


def listar_lancamentos(inicio: date | None = None, fim: date | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM financeiro"
    params: list[Any] = []
    if inicio and fim:
        sql += " WHERE data BETWEEN %s AND %s"
        params.extend([_iso_date(inicio), _iso_date(fim)])
    sql += " ORDER BY data DESC, id DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _as_dicts(rows)


def salvar_lancamento(
    tipo: str,
    categoria: str,
    descricao: str,
    valor: float,
    data_lancamento: date | str,
    lancamento_id: int | None = None,
) -> int:
    dia = _iso_date(data_lancamento)
    with get_connection() as conn:
        if lancamento_id:
            conn.execute(
                """
                UPDATE financeiro
                SET tipo = %s, categoria = %s, descricao = %s, valor = %s, data = %s
                WHERE id = %s AND agendamento_id IS NULL
                """,
                (tipo, categoria, descricao.strip(), valor, dia, lancamento_id),
            )
            return lancamento_id

        cur = conn.execute(
            """
            INSERT INTO financeiro (tipo, categoria, descricao, valor, data)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (tipo, categoria, descricao.strip(), valor, dia),
        )
        res = cur.fetchone()
        return int(res["id"])


def excluir_lancamento(lancamento_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM financeiro WHERE id = %s AND agendamento_id IS NULL",
            (lancamento_id,),
        )


def resumo_financeiro(inicio: date, fim: date) -> dict[str, float]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN tipo = 'Receita' THEN valor END), 0) AS receitas,
                COALESCE(SUM(CASE WHEN tipo = 'Despesa' THEN valor END), 0) AS despesas
            FROM financeiro
            WHERE data BETWEEN %s AND %s
            """,
            (_iso_date(inicio), _iso_date(fim)),
        ).fetchone()
    receitas = float(row["receitas"]) if row and row.get("receitas") is not None else 0.0
    despesas = float(row["despesas"]) if row and row.get("despesas") is not None else 0.0
    return {
        "receitas": receitas,
        "despesas": despesas,
        "lucro": receitas - despesas,
    }


def media_faturamento_dias_uteis(inicio: date, fim: date) -> float:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT data, SUM(valor) AS total
            FROM financeiro
            WHERE tipo = 'Receita' AND data BETWEEN %s AND %s
            GROUP BY data
            """,
            (_iso_date(inicio), _iso_date(fim)),
        ).fetchall()
    totais = [float(row["total"]) for row in rows if date.fromisoformat(str(row["data"])).weekday() < 5]
    if not totais:
        return 0.0
    return sum(totais) / len(totais)


def ticket_medio(inicio: date, fim: date) -> float:
    inicio_txt = f"{_iso_date(inicio)} 00:00:00"
    fim_txt = f"{_iso_date(fim)} 23:59:59"
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT AVG(COALESCE(a.valor_cobrado, s.preco_padrao, 0)) AS media
            FROM agendamentos a
            JOIN servicos s ON s.id = a.servico_id
            WHERE a.status = 'Concluído'
              AND a.data_hora BETWEEN %s AND %s
            """,
            (inicio_txt, fim_txt),
        ).fetchone()
    return float(row["media"]) if row and row.get("media") is not None else 0.0


def faturamento_semanal(inicio: date, fim: date) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT data, SUM(valor) AS total
            FROM financeiro
            WHERE tipo = 'Receita' AND data BETWEEN %s AND %s
            GROUP BY data
            ORDER BY data
            """,
            (_iso_date(inicio), _iso_date(fim)),
        ).fetchall()
    por_dia = {str(row["data"]): float(row["total"]) for row in rows}
    semanas: dict[str, float] = {}
    cursor = inicio
    while cursor <= fim:
        segunda = cursor - timedelta(days=cursor.weekday())
        chave = segunda.isoformat()
        semanas[chave] = semanas.get(chave, 0.0) + por_dia.get(cursor.isoformat(), 0.0)
        cursor += timedelta(days=1)
    return [{"semana": chave, "total": total} for chave, total in semanas.items()]


def faturamento_mensal(ano: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT SUBSTRING(data FROM 1 FOR 7) AS mes, SUM(valor) AS total
            FROM financeiro
            WHERE tipo = 'Receita' AND SUBSTRING(data FROM 1 FOR 4) = %s
            GROUP BY mes
            ORDER BY mes
            """,
            (str(ano),),
        ).fetchall()
    mapa = {str(row["mes"]): float(row["total"]) for row in rows}
    return [
        {"mes": f"{ano}-{mes:02d}", "total": mapa.get(f"{ano}-{mes:02d}", 0.0)}
        for mes in range(1, 13)
    ]


def faturamento_por_servico(inicio: date, fim: date) -> list[dict[str, Any]]:
    inicio_txt = f"{_iso_date(inicio)} 00:00:00"
    fim_txt = f"{_iso_date(fim)} 23:59:59"
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.nome AS servico,
                   SUM(COALESCE(a.valor_cobrado, s.preco_padrao, 0)) AS total
            FROM agendamentos a
            JOIN servicos s ON s.id = a.servico_id
            WHERE a.status = 'Concluído'
              AND a.data_hora BETWEEN %s AND %s
            GROUP BY s.id, s.nome
            ORDER BY total DESC
            """,
            (inicio_txt, fim_txt),
        ).fetchall()
    return _as_dicts(rows)


def combinar_data_hora(dia: date, hora: time) -> datetime:
    return datetime.combine(dia, hora)
