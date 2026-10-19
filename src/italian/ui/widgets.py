"""Универсальные виджеты: форма редактирования и вкладка-справочник с таблицей."""

from __future__ import annotations

import datetime as dt
import enum
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from PyQt6.QtCore import QDate, QSortFilterProxyModel, Qt, QTime
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

SORT_ROLE = Qt.ItemDataRole.UserRole
ID_ROLE = Qt.ItemDataRole.UserRole + 1
NO_DATE = QDate(1900, 1, 1)

PHONE_RE = re.compile(r"^\+?\d[\d\- ()]{5,18}\d$")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def check_phone(value: str | None) -> str | None:
    if value and not PHONE_RE.match(value):
        return "Телефон должен содержать только цифры, пробелы, «+», «-» и скобки"
    return None


def check_email(value: str | None) -> str | None:
    if value and not EMAIL_RE.match(value):
        return "Некорректный адрес e-mail"
    return None


def fmt(value: Any) -> str:
    """Отображение значения в таблице."""
    match value:
        case None:
            return ""
        case bool():
            return "да" if value else "нет"
        case Decimal() | float():
            return f"{value:,.2f}".replace(",", " ")
        case dt.date():
            return value.strftime("%d.%m.%Y")
        case dt.time():
            return value.strftime("%H:%M")
        case enum.Enum():
            return str(value.value)
        case _:
            return str(value)


def sort_key(value: Any) -> Any:
    match value:
        case None:
            return ""
        case bool():
            return int(value)
        case Decimal():
            return float(value)
        case dt.date() | dt.time():
            return value.isoformat()
        case int() | float():
            return value
        case _:
            return str(value).lower()


@dataclass
class Field:
    """Поле формы. kind: str, int, money, date, time, bool, enum, fk."""

    attr: str
    label: str
    kind: str = "str"
    required: bool = True
    options: Any = None  # класс перечисления или ORM-модель для fk
    validator: Callable[[Any], str | None] | None = None
    minimum: int = 0
    maximum: int = 10_000


@dataclass
class Column:
    label: str
    getter: Callable[[Any], Any]


@dataclass
class EntitySpec:
    model: type
    title: str
    singular: str
    fields: list[Field]
    columns: list[Column]
    # Бизнес-проверка: (сессия, редактируемый объект или None, значения) -> текст ошибки.
    validate: Callable[[Session, Any, dict[str, Any]], str | None] | None = None
    defaults: dict[str, Any] = field(default_factory=dict)
    order_by: Any = None


class EntityDialog(QDialog):
    def __init__(
        self,
        spec: EntitySpec,
        session: Session,
        obj: Any = None,
        fk_scopes: dict[str, Callable[[Select], Select]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.spec = spec
        self.session = session
        self.obj = obj
        self.values: dict[str, Any] = {}
        self.setWindowTitle(("Изменение: " if obj else "Добавление: ") + spec.singular)
        self.setMinimumWidth(420)

        form = QFormLayout()
        self.editors: dict[str, QWidget] = {}
        for f in spec.fields:
            initial = (
                getattr(obj, f.attr) if obj is not None else spec.defaults.get(f.attr)
            )
            editor = self._make_editor(f, initial, (fk_scopes or {}).get(f.attr))
            self.editors[f.attr] = editor
            form.addRow(
                f.label + (" *" if f.required and f.kind != "bool" else ""), editor
            )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        hint = QLabel("* — обязательные поля")
        hint.setStyleSheet("color: gray")
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def _make_editor(
        self, f: Field, value: Any, scope: Callable[[Select], Select] | None
    ) -> QWidget:
        match f.kind:
            case "int":
                w = QSpinBox()
                w.setRange(f.minimum, f.maximum)
                w.setValue(value if value is not None else f.minimum)
            case "money":
                w = QDoubleSpinBox()
                w.setRange(0, 10_000_000)
                w.setDecimals(2)
                w.setSingleStep(1000)
                w.setSuffix(" ₽")
                w.setGroupSeparatorShown(True)
                w.setValue(float(value) if value is not None else 0)
            case "date":
                w = QDateEdit()
                w.setCalendarPopup(True)
                w.setDisplayFormat("dd.MM.yyyy")
                if not f.required:
                    w.setMinimumDate(NO_DATE)
                    w.setSpecialValueText("не указана")
                if value is not None:
                    w.setDate(QDate(value.year, value.month, value.day))
                else:
                    w.setDate(NO_DATE if not f.required else QDate.currentDate())
            case "time":
                w = QTimeEdit()
                w.setDisplayFormat("HH:mm")
                w.setTime(QTime(value.hour, value.minute) if value else QTime(18, 0))
            case "bool":
                w = QCheckBox()
                w.setChecked(bool(value))
            case "enum":
                w = QComboBox()
                for member in f.options:
                    w.addItem(member.value, member)
                if value is not None:
                    w.setCurrentIndex(w.findData(value))
            case "fk":
                w = QComboBox()
                query = select(f.options)
                if scope:
                    query = scope(query)
                items = sorted(self.session.scalars(query), key=str)
                for item in items:
                    w.addItem(str(item), item.id)
                if value is not None:
                    w.setCurrentIndex(w.findData(value))
            case _:
                w = QLineEdit()
                w.setText(value or "")
        return w

    def _read(self, f: Field) -> Any:
        w = self.editors[f.attr]
        match f.kind:
            case "int":
                return w.value()
            case "money":
                return Decimal(str(round(w.value(), 2)))
            case "date":
                return None if w.date() == NO_DATE else w.date().toPyDate()
            case "time":
                return w.time().toPyTime()
            case "bool":
                return w.isChecked()
            case "enum" | "fk":
                return w.currentData()
            case _:
                return w.text().strip() or None

    def _on_accept(self) -> None:
        values = {f.attr: self._read(f) for f in self.spec.fields}
        for f in self.spec.fields:
            value = values[f.attr]
            if f.required and value is None:
                return self._error(f"Заполните поле «{f.label}».", f)
            if f.kind == "money" and f.required and value <= 0:
                return self._error(f"Поле «{f.label}» должно быть больше нуля.", f)
            if f.validator and (msg := f.validator(value)):
                return self._error(msg, f)
        if self.spec.validate and (
            msg := self.spec.validate(self.session, self.obj, values)
        ):
            return self._error(msg)
        self.values = values
        self.accept()

    def _error(self, message: str, f: Field | None = None) -> None:
        QMessageBox.warning(self, "Проверка данных", message)
        if f is not None:
            self.editors[f.attr].setFocus()


class EntityTab(QWidget):
    """Таблица записей с поиском и кнопками «Добавить / Изменить / Удалить»."""

    def __init__(
        self,
        spec: EntitySpec,
        session_factory: sessionmaker[Session],
        *,
        can_add: bool = True,
        can_edit: bool = True,
        can_delete: bool = True,
        scope: Callable[[Select], Select] | None = None,
        fk_scopes: dict[str, Callable[[Select], Select]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.spec = spec
        self.session_factory = session_factory
        self.scope = scope
        self.fk_scopes = fk_scopes
        self.can_edit = can_edit

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск…")
        self.search.setClearButtonEnabled(True)

        self.model = QStandardItemModel(0, len(spec.columns), self)
        self.model.setHorizontalHeaderLabels([c.label for c in spec.columns])
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(SORT_ROLE)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        self.buttons: list[QPushButton] = []
        for text, slot, enabled in (
            ("Добавить", self.add, can_add),
            ("Изменить", self.edit, can_edit),
            ("Удалить", self.delete, can_delete),
        ):
            if enabled:
                btn = QPushButton(text)
                btn.clicked.connect(slot)
                top.addWidget(btn)
                self.buttons.append(btn)
        btn = QPushButton("Обновить")
        btn.clicked.connect(self.refresh)
        top.addWidget(btn)

        self.counter = QLabel()
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(self.counter)

        if can_edit:
            self.table.doubleClicked.connect(lambda _: self.edit())
        self.proxy.rowsInserted.connect(self._update_counter)
        self.proxy.rowsRemoved.connect(self._update_counter)
        self.proxy.modelReset.connect(self._update_counter)
        self.proxy.layoutChanged.connect(self._update_counter)

    def _query(self) -> Select:
        query = select(self.spec.model)
        if self.scope:
            query = self.scope(query)
        order = self.spec.order_by
        if order is not None:
            query = query.order_by(*(order if isinstance(order, tuple) else (order,)))
        return query

    def refresh(self) -> None:
        selected = self.selected_id()
        self.model.removeRows(0, self.model.rowCount())
        with self.session_factory() as session:
            for obj in session.scalars(self._query()).unique():
                row = []
                for column in self.spec.columns:
                    value = column.getter(obj)
                    item = QStandardItem(fmt(value))
                    item.setData(sort_key(value), SORT_ROLE)
                    if isinstance(value, (int, float, Decimal)) and not isinstance(
                        value, bool
                    ):
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    row.append(item)
                row[0].setData(obj.id, ID_ROLE)
                self.model.appendRow(row)
        self.table.resizeColumnsToContents()
        if selected is not None:
            self.select_id(selected)
        self._update_counter()

    def _update_counter(self, *_: Any) -> None:
        total, shown = self.model.rowCount(), self.proxy.rowCount()
        text = f"Записей: {total}"
        if shown != total:
            text += f" (показано {shown})"
        self.counter.setText(text)

    def selected_id(self) -> int | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.proxy.index(indexes[0].row(), 0).data(ID_ROLE)

    def select_id(self, obj_id: int) -> None:
        for row in range(self.proxy.rowCount()):
            if self.proxy.index(row, 0).data(ID_ROLE) == obj_id:
                self.table.selectRow(row)
                return

    def add(self) -> None:
        self._open_dialog(None)

    def edit(self) -> None:
        obj_id = self.selected_id()
        if obj_id is None:
            QMessageBox.information(self, self.spec.title, "Выберите запись в таблице.")
            return
        self._open_dialog(obj_id)

    def _open_dialog(self, obj_id: int | None) -> None:
        with self.session_factory() as session:
            obj = session.get(self.spec.model, obj_id) if obj_id is not None else None
            dialog = EntityDialog(self.spec, session, obj, self.fk_scopes, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if obj is None:
                obj = self.spec.model()
                session.add(obj)
            for attr, value in dialog.values.items():
                setattr(obj, attr, value)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                QMessageBox.critical(self, "Ошибка сохранения", integrity_message(exc))
                return
            new_id = obj.id
        self.refresh()
        self.select_id(new_id)

    def delete(self) -> None:
        obj_id = self.selected_id()
        if obj_id is None:
            QMessageBox.information(self, self.spec.title, "Выберите запись в таблице.")
            return
        with self.session_factory() as session:
            obj = session.get(self.spec.model, obj_id)
            answer = QMessageBox.question(
                self, "Удаление", f"Удалить запись «{obj}» ({self.spec.singular})?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            session.delete(obj)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                QMessageBox.critical(
                    self,
                    "Удаление невозможно",
                    "На запись ссылаются другие данные (группы, зачисления, занятия). "
                    "Сначала удалите или измените связанные записи.",
                )
                return
        self.refresh()


CONSTRAINT_MESSAGES = {
    "uq_enrollment": "Этот слушатель уже зачислен в выбранную группу.",
    "classroom_number_key": "Аудитория с таким номером уже существует.",
    "uq_lesson_room_time": "Аудитория в это время уже занята.",
    "ck_course_hours": "Количество часов должно быть больше нуля.",
    "ck_course_price": "Стоимость не может быть отрицательной.",
    "ck_classroom_capacity": "Вместимость должна быть больше нуля.",
    "ck_payment_amount": "Сумма оплаты должна быть больше нуля.",
}


def integrity_message(exc: IntegrityError) -> str:
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint in CONSTRAINT_MESSAGES:
        return CONSTRAINT_MESSAGES[constraint]
    if constraint and constraint.endswith("_fkey"):
        return "Нарушена ссылочная целостность: связанная запись не найдена."
    return f"Данные не сохранены: {exc.orig}"
