"""Helpers de data, telefone e formatação."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

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
