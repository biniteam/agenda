"""Helpers de data, telefone e formatação."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo
from dateutil.rrule import rrulestr

TZ = ZoneInfo("America/Sao_Paulo")
MESES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
DIAS_SEMANA = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
MAPA_DIAS_RRULE = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
STATUS_AGENDAMENTO = ("Agendado", "Em Andamento", "Concluído", "Cancelado")
PORTES = ("P", "M", "G")
CATEGORIAS_RECEITA = ("Serviços", "Produtos", "Outros")
CATEGORIAS_DESPESA = ("Produtos", "Aluguel", "Energia", "Salários", "Outros")


def hoje() -> date:
    return datetime.now(TZ).date()


def agora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def inicio_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def fim_semana(dia: date) -> date:
    return inicio_semana(dia) + timedelta(days=6)


def rotulo_mes(dia: date) -> str:
    return f"{MESES[dia.month - 1]} {dia.year}"


def formatar_moeda(valor: float | None) -> str:
    numero = float(valor or 0)
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def somente_digitos(telefone: str | None) -> str:
    return "".join(ch for ch in (telefone or "") if ch.isdigit())


def link_whatsapp(telefone: str | None, mensagem: str) -> str | None:
    digitos = somente_digitos(telefone)
    if not digitos:
        return None
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return f"https://wa.me/{digitos}?text={quote(mensagem)}"


def construir_rrule(frequencia: str, dias_semana_indices: list[int] | None = None) -> str | None:
    """
    Gera uma string RRULE válida com base nas opções da interface.
    frequencia: 'Diário', 'Semanal', 'Quinzenal', 'Mensal'
    dias_semana_indices: lista de inteiros 0=Segunda, 1=Terça, ..., 6=Domingo
    """
    if frequencia == "Diário":
        return "FREQ=DAILY"
    elif frequencia == "Semanal":
        if not dias_semana_indices:
            return "FREQ=WEEKLY"
        dias_str = ",".join(MAPA_DIAS_RRULE[i] for i in sorted(dias_semana_indices))
        return f"FREQ=WEEKLY;BYDAY={dias_str}"
    elif frequencia == "Quinzenal":
        if not dias_semana_indices:
            return "FREQ=WEEKLY;INTERVAL=2"
        dias_str = ",".join(MAPA_DIAS_RRULE[i] for i in sorted(dias_semana_indices))
        return f"FREQ=WEEKLY;INTERVAL=2;BYDAY={dias_str}"
    elif frequencia == "Mensal":
        return "FREQ=MONTHLY"
    return None


def decodificar_rrule(rrule_str: str | None) -> dict:
    """
    Analisa uma string RRULE e retorna um dicionário com frequencia e dias da semana para pré-preencher o formulário.
    """
    if not rrule_str:
        return {"repetir": False, "frequencia": "Diário", "dias_semana": []}

    res = {"repetir": True, "frequencia": "Diário", "dias_semana": []}
    try:
        rule = rrulestr(rrule_str)
        freq_map = {0: "Yearly", 1: "Mensal", 2: "Semanal", 3: "Diário"}
        freq_nome = freq_map.get(rule._freq, "Diário")

        if freq_nome == "Semanal" and rule._interval == 2:
            freq_nome = "Quinzenal"

        res["frequencia"] = freq_nome

        if rule._byweekday:
            res["dias_semana"] = list(rule._byweekday)
    except Exception:
        pass

    return res
