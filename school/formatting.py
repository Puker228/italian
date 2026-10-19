"""Единое отображение значений в таблицах, отчётах и CSV."""

import datetime as dt
from decimal import Decimal
from typing import Any


def fmt(value: Any) -> str:
    match value:
        case None | "":
            return ""
        case bool():
            return "да" if value else "нет"
        case Decimal() | float():
            return f"{value:,.2f}".replace(",", " ")
        case dt.date():
            return value.strftime("%d.%m.%Y")
        case dt.time():
            return value.strftime("%H:%M")
        case _:
            return str(value)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
