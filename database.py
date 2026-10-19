"""Conexão SQLite, schema e consultas do pet shop."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "petshop.db"

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


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telefone TEXT,
                endereco TEXT,
                observacoes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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

            CREATE TABLE IF NOT EXISTS servicos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                preco_padrao REAL NOT NULL DEFAULT 0,
                duracao_minutos INTEGER NOT NULL DEFAULT 60
            );

            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                servico_id INTEGER NOT NULL,
                data_hora TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Agendado',
                profissional TEXT,
                valor_cobrado REAL,
                observacoes TEXT,
                FOREIGN KEY (pet_id) REFERENCES pets(id),
                FOREIGN KEY (servico_id) REFERENCES servicos(id)
            );

            CREATE TABLE IF NOT EXISTS financeiro (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                categoria TEXT,
                descricao TEXT,
                valor REAL NOT NULL,
                data TEXT NOT NULL,
                agendamento_id INTEGER,
                FOREIGN KEY (agendamento_id) REFERENCES agendamentos(id)
            );
            """
        )
        _seed_servicos(conn)


def _seed_servicos(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM servicos").fetchone()[0]
    if count:
        return
    conn.executemany(
        "INSERT INTO servicos (nome, preco_padrao, duracao_minutos) VALUES (?, ?, ?)",
        SERVICOS_PADRAO,
    )


def _as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
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
            ORDER BY c.nome COLLATE NOCASE
            """
        ).fetchall()
    return _as_dicts(rows)


def obter_cliente(cliente_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
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
                SET nome = ?, telefone = ?, endereco = ?, observacoes = ?
                WHERE id = ?
                """,
                (nome.strip(), telefone.strip(), endereco.strip(), observacoes.strip(), cliente_id),
            )
            return cliente_id
        cursor = conn.execute(
            """
            INSERT INTO clientes (nome, telefone, endereco, observacoes)
            VALUES (?, ?, ?, ?)
            """,
            (nome.strip(), telefone.strip(), endereco.strip(), observacoes.strip()),
        )
        return int(cursor.lastrowid)


def excluir_cliente(cliente_id: int) -> None:
    with get_connection() as conn:
        pets = conn.execute(
            "SELECT id FROM pets WHERE cliente_id = ?", (cliente_id,)
        ).fetchall()
        pet_ids = [row["id"] for row in pets]
        if pet_ids:
            placeholders = ",".join("?" * len(pet_ids))
            conn.execute(
                f"DELETE FROM financeiro WHERE agendamento_id IN "
                f"(SELECT id FROM agendamentos WHERE pet_id IN ({placeholders}))",
                pet_ids,
            )
            conn.execute(
                f"DELETE FROM agendamentos WHERE pet_id IN ({placeholders})",
                pet_ids,
            )
            conn.execute("DELETE FROM pets WHERE cliente_id = ?", (cliente_id,))
        conn.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))


# --- Pets ---


def listar_pets(cliente_id: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT p.*, c.nome AS tutor_nome, c.telefone AS tutor_telefone
        FROM pets p
        JOIN clientes c ON c.id = p.cliente_id
    """
    params: tuple[Any, ...] = ()
    if cliente_id is not None:
        sql += " WHERE p.cliente_id = ?"
        params = (cliente_id,)
    sql += " ORDER BY c.nome COLLATE NOCASE, p.nome COLLATE NOCASE"
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
            WHERE p.id = ?
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
                SET cliente_id = ?, nome = ?, especie = ?, raca = ?, porte = ?,
                    pelagem = ?, data_nascimento = ?, temperamento = ?,
                    alergias_restricoes = ?
                WHERE id = ?
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
        cursor = conn.execute(
            """
            INSERT INTO pets (
                cliente_id, nome, especie, raca, porte, pelagem,
                data_nascimento, temperamento, alergias_restricoes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        return int(cursor.lastrowid)


def excluir_pet(pet_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM financeiro WHERE agendamento_id IN "
            "(SELECT id FROM agendamentos WHERE pet_id = ?)",
            (pet_id,),
        )
        conn.execute("DELETE FROM agendamentos WHERE pet_id = ?", (pet_id,))
        conn.execute("DELETE FROM pets WHERE id = ?", (pet_id,))


def prontuario_pet(pet_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            AGENDAMENTO_SELECT + " WHERE a.pet_id = ? ORDER BY a.data_hora DESC",
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
              AND strftime('%m-%d', p.data_nascimento) = ?
            ORDER BY p.nome COLLATE NOCASE
            """,
            (chave,),
        ).fetchall()
    return _as_dicts(rows)


# --- Serviços ---


def listar_servicos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM servicos ORDER BY nome COLLATE NOCASE"
        ).fetchall()
    return _as_dicts(rows)


# --- Agendamentos ---


def listar_agendamentos(inicio: date, fim: date) -> list[dict[str, Any]]:
    inicio_txt = f"{_iso_date(inicio)} 00:00:00"
    fim_txt = f"{_iso_date(fim)} 23:59:59"
    with get_connection() as conn:
        rows = conn.execute(
            AGENDAMENTO_SELECT
            + " WHERE a.data_hora BETWEEN ? AND ? ORDER BY a.data_hora",
            (inicio_txt, fim_txt),
        ).fetchall()
    return _as_dicts(rows)


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
        chave = item["data_hora"][:10]
        bucket = totais.setdefault(chave, {"qtd": 0, "valor": 0.0})
        bucket["qtd"] += 1
        bucket["valor"] += float(item["valor_estimado"] or 0)
    return totais


def obter_agendamento(agendamento_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            AGENDAMENTO_SELECT + " WHERE a.id = ?", (agendamento_id,)
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
    agendamento_id: int | None = None,
) -> int:
    instante = _iso_datetime(data_hora)
    with get_connection() as conn:
        if agendamento_id:
            conn.execute(
                """
                UPDATE agendamentos
                SET pet_id = ?, servico_id = ?, data_hora = ?, status = ?,
                    profissional = ?, valor_cobrado = ?, observacoes = ?
                WHERE id = ?
                """,
                (
                    pet_id,
                    servico_id,
                    instante,
                    status,
                    profissional.strip(),
                    valor_cobrado,
                    observacoes.strip(),
                    agendamento_id,
                ),
            )
            novo_id = agendamento_id
        else:
            cursor = conn.execute(
                """
                INSERT INTO agendamentos (
                    pet_id, servico_id, data_hora, status, profissional,
                    valor_cobrado, observacoes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pet_id,
                    servico_id,
                    instante,
                    status,
                    profissional.strip(),
                    valor_cobrado,
                    observacoes.strip(),
                ),
            )
            novo_id = int(cursor.lastrowid)
    _sincronizar_receita_agendamento(novo_id)
    return novo_id


def atualizar_status_agendamento(agendamento_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE agendamentos SET status = ? WHERE id = ?",
            (status, agendamento_id),
        )
    _sincronizar_receita_agendamento(agendamento_id)


def excluir_agendamento(agendamento_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM financeiro WHERE agendamento_id = ?", (agendamento_id,)
        )
        conn.execute("DELETE FROM agendamentos WHERE id = ?", (agendamento_id,))


def _sincronizar_receita_agendamento(agendamento_id: int) -> None:
    agendamento = obter_agendamento(agendamento_id)
    if agendamento is None:
        return
    with get_connection() as conn:
        existente = conn.execute(
            "SELECT id FROM financeiro WHERE agendamento_id = ? AND tipo = 'Receita'",
            (agendamento_id,),
        ).fetchone()
        if agendamento["status"] != "Concluído":
            if existente:
                conn.execute("DELETE FROM financeiro WHERE id = ?", (existente["id"],))
            return
        valor = float(agendamento["valor_estimado"] or 0)
        dia = agendamento["data_hora"][:10]
        descricao = (
            f"{agendamento['servico_nome']} — {agendamento['pet_nome']} "
            f"({agendamento['tutor_nome']})"
        )
        if existente:
            conn.execute(
                """
                UPDATE financeiro
                SET categoria = 'Serviços', descricao = ?, valor = ?, data = ?
                WHERE id = ?
                """,
                (descricao, valor, dia, existente["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO financeiro (tipo, categoria, descricao, valor, data, agendamento_id)
                VALUES ('Receita', 'Serviços', ?, ?, ?, ?)
                """,
                (descricao, valor, dia, agendamento_id),
            )


# --- Financeiro ---


def listar_lancamentos(inicio: date | None = None, fim: date | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM financeiro"
    params: list[Any] = []
    if inicio and fim:
        sql += " WHERE data BETWEEN ? AND ?"
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
                SET tipo = ?, categoria = ?, descricao = ?, valor = ?, data = ?
                WHERE id = ? AND agendamento_id IS NULL
                """,
                (tipo, categoria, descricao.strip(), valor, dia, lancamento_id),
            )
            return lancamento_id
        cursor = conn.execute(
            """
            INSERT INTO financeiro (tipo, categoria, descricao, valor, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tipo, categoria, descricao.strip(), valor, dia),
        )
        return int(cursor.lastrowid)


def excluir_lancamento(lancamento_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM financeiro WHERE id = ? AND agendamento_id IS NULL",
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
            WHERE data BETWEEN ? AND ?
            """,
            (_iso_date(inicio), _iso_date(fim)),
        ).fetchone()
    receitas = float(row["receitas"])
    despesas = float(row["despesas"])
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
            WHERE tipo = 'Receita' AND data BETWEEN ? AND ?
            GROUP BY data
            """,
            (_iso_date(inicio), _iso_date(fim)),
        ).fetchall()
    totais = [float(row["total"]) for row in rows if date.fromisoformat(row["data"]).weekday() < 5]
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
              AND a.data_hora BETWEEN ? AND ?
            """,
            (inicio_txt, fim_txt),
        ).fetchone()
    return float(row["media"] or 0)


def faturamento_semanal(inicio: date, fim: date) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT data, SUM(valor) AS total
            FROM financeiro
            WHERE tipo = 'Receita' AND data BETWEEN ? AND ?
            GROUP BY data
            ORDER BY data
            """,
            (_iso_date(inicio), _iso_date(fim)),
        ).fetchall()
    por_dia = {row["data"]: float(row["total"]) for row in rows}
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
            SELECT substr(data, 1, 7) AS mes, SUM(valor) AS total
            FROM financeiro
            WHERE tipo = 'Receita' AND substr(data, 1, 4) = ?
            GROUP BY mes
            ORDER BY mes
            """,
            (str(ano),),
        ).fetchall()
    mapa = {row["mes"]: float(row["total"]) for row in rows}
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
              AND a.data_hora BETWEEN ? AND ?
            GROUP BY s.id, s.nome
            ORDER BY total DESC
            """,
            (inicio_txt, fim_txt),
        ).fetchall()
    return _as_dicts(rows)


def combinar_data_hora(dia: date, hora: time) -> datetime:
    return datetime.combine(dia, hora)
