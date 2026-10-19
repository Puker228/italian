"""Вкладка «Отчёты»: должники, поступления, наполняемость групп, нагрузка преподавателей."""

from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from italian.models import Enrollment, EnrollmentStatus, Group, Lesson, Payment, Teacher
from italian.ui.widgets import fmt

Report = tuple[list[str], list[list[Any]], str]


def debtors(session: Session, start: dt.date, end: dt.date) -> Report:
    rows, total = [], Decimal(0)
    query = select(Enrollment).where(Enrollment.status == EnrollmentStatus.ACTIVE)
    for e in session.scalars(query):
        debt = e.get_debt()
        if debt > 0:
            rows.append(
                [
                    e.student,
                    e.student.phone,
                    e.group,
                    e.group.course.price,
                    e.get_paid(),
                    debt,
                ]
            )
            total += debt
    rows.sort(key=lambda r: r[-1], reverse=True)
    header = [
        "Слушатель",
        "Телефон",
        "Группа",
        "Стоимость, ₽",
        "Оплачено, ₽",
        "Долг, ₽",
    ]
    return header, rows, f"Должников: {len(rows)}, общая задолженность: {fmt(total)} ₽"


def income(session: Session, start: dt.date, end: dt.date) -> Report:
    query = (
        select(Payment)
        .where(Payment.pay_date.between(start, end))
        .order_by(Payment.pay_date)
    )
    rows = [
        [p.pay_date, p.enrollment.student, p.enrollment.group, p.amount]
        for p in session.scalars(query)
    ]
    total = sum((r[-1] for r in rows), Decimal(0))
    return (
        ["Дата", "Слушатель", "Группа", "Сумма, ₽"],
        rows,
        f"Платежей: {len(rows)}, поступило: {fmt(total)} ₽",
    )


def group_fill(session: Session, start: dt.date, end: dt.date) -> Report:
    rows = []
    for g in session.scalars(select(Group).order_by(Group.name)):
        lessons = [les for les in g.lessons if start <= les.lesson_date <= end]
        rows.append(
            [g, g.course, g.teacher, g.start_date, len(g.get_students()), len(lessons)]
        )
    return (
        ["Группа", "Курс", "Преподаватель", "Старт", "Слушателей", "Занятий за период"],
        rows,
        f"Групп: {len(rows)}, слушателей: {sum(r[4] for r in rows)}",
    )


def teacher_load(session: Session, start: dt.date, end: dt.date) -> Report:
    rows = []
    for t in session.scalars(select(Teacher).order_by(Teacher.last_name)):
        lessons = [les for les in t.get_schedule() if start <= les.lesson_date <= end]
        rows.append([t, t.is_native, len(t.groups), len(lessons)])
    return (
        ["Преподаватель", "Носитель языка", "Групп", "Занятий за период"],
        rows,
        f"Всего занятий за период: {sum(r[3] for r in rows)}",
    )


def schedule(session: Session, start: dt.date, end: dt.date) -> Report:
    query = (
        select(Lesson)
        .where(Lesson.lesson_date.between(start, end))
        .order_by(Lesson.lesson_date, Lesson.start_time)
    )
    rows = [
        [
            les.lesson_date,
            les.start_time,
            les.group,
            les.group.teacher,
            les.classroom.number,
            les.topic,
        ]
        for les in session.scalars(query)
    ]
    return (
        ["Дата", "Время", "Группа", "Преподаватель", "Аудитория", "Тема"],
        rows,
        f"Занятий: {len(rows)}",
    )


REPORTS: dict[str, Callable[[Session, dt.date, dt.date], Report]] = {
    "Должники по оплате": debtors,
    "Поступления оплат за период": income,
    "Наполняемость групп": group_fill,
    "Нагрузка преподавателей": teacher_load,
    "Расписание на период": schedule,
}


class ReportsTab(QWidget):
    def __init__(
        self, session_factory: sessionmaker[Session], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory

        self.kind = QComboBox()
        self.kind.addItems(REPORTS)
        today = QDate.currentDate()
        self.start = QDateEdit(QDate(today.year(), 1, 1))
        self.end = QDateEdit(today.addMonths(1))
        for w in (self.start, self.end):
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy")

        build = QPushButton("Сформировать")
        build.clicked.connect(self.refresh)
        export = QPushButton("Экспорт в CSV")
        export.clicked.connect(self.export)
        self.kind.currentIndexChanged.connect(self.refresh)

        top = QHBoxLayout()
        top.addWidget(QLabel("Отчёт:"))
        top.addWidget(self.kind, 1)
        top.addWidget(QLabel("с"))
        top.addWidget(self.start)
        top.addWidget(QLabel("по"))
        top.addWidget(self.end)
        top.addWidget(build)
        top.addWidget(export)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(self.summary)

    def refresh(self) -> None:
        start, end = self.start.date().toPyDate(), self.end.date().toPyDate()
        if start > end:
            QMessageBox.warning(
                self, "Отчёты", "Дата начала периода позже даты окончания."
            )
            return
        with self.session_factory() as session:
            header, rows, summary = REPORTS[self.kind.currentText()](
                session, start, end
            )
            text_rows = [[fmt(v) for v in row] for row in rows]
            numeric = [
                [isinstance(v, (int, Decimal)) and not isinstance(v, bool) for v in row]
                for row in rows
            ]
        self.table.clear()
        self.table.setColumnCount(len(header))
        self.table.setHorizontalHeaderLabels(header)
        self.table.setRowCount(len(text_rows))
        for r, row in enumerate(text_rows):
            for c, text in enumerate(row):
                item = QTableWidgetItem(text)
                if numeric[r][c]:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.summary.setText(summary)

    def export(self) -> None:
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "Экспорт", "Сначала сформируйте отчёт.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчёт", f"{self.kind.currentText()}.csv", "CSV (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                self.table.horizontalHeaderItem(c).text()
                for c in range(self.table.columnCount())
            )
            for r in range(self.table.rowCount()):
                writer.writerow(
                    self.table.item(r, c).text()
                    for c in range(self.table.columnCount())
                )
            writer.writerow([self.summary.text()])
        QMessageBox.information(self, "Экспорт", f"Отчёт сохранён:\n{path}")
