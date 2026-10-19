"""Окно входа (выбор роли) и главное окно приложения."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine, Select, select
from sqlalchemy.orm import Session, sessionmaker

from italian.db import backup
from italian.models import Enrollment, EnrollmentStatus, Group, Student, Teacher
from italian.ui import specs
from italian.ui.reports import ReportsTab
from italian.ui.widgets import EntityTab


class Role(StrEnum):
    ADMIN = "Администратор"
    TEACHER = "Преподаватель"
    STUDENT = "Слушатель"


@dataclass
class User:
    role: Role
    person_id: int | None = None
    name: str = ""


class LoginDialog(QDialog):
    def __init__(
        self, session_factory: sessionmaker[Session], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.setWindowTitle("Вход в систему")
        self.setMinimumWidth(380)

        title = QLabel("<h3>Школа изучения итальянского языка</h3>")
        self.role = QComboBox()
        for role in Role:
            self.role.addItem(role.value, role)
        self.person = QComboBox()
        self.person_label = QLabel()

        form = QFormLayout()
        form.addRow("Роль:", self.role)
        form.addRow(self.person_label, self.person)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Войти")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Выход")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.role.currentIndexChanged.connect(self._fill_people)
        self._fill_people()
        self.user: User | None = None

    def _fill_people(self) -> None:
        role = self.role.currentData()
        self.person.clear()
        model = {Role.TEACHER: Teacher, Role.STUDENT: Student}.get(role)
        visible = model is not None
        self.person.setVisible(visible)
        self.person_label.setVisible(visible)
        if model is None:
            return
        self.person_label.setText(f"{role.value}:")
        with self.session_factory() as session:
            for person in session.scalars(select(model).order_by(model.last_name)):
                self.person.addItem(person.get_full_name(), person.id)

    def _on_accept(self) -> None:
        role = self.role.currentData()
        if role != Role.ADMIN and self.person.currentData() is None:
            QMessageBox.warning(
                self, "Вход", f"В базе нет ни одной записи «{role.value}»."
            )
            return
        if role == Role.ADMIN:
            self.user = User(role)
        else:
            self.user = User(role, self.person.currentData(), self.person.currentText())
        self.accept()


class MainWindow(QMainWindow):
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        engine: Engine,
        user: User,
    ) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.engine = engine
        self.user = user
        self.switch_user = False

        self.setWindowTitle("ИС «Школа изучения итальянского языка»")
        self.resize(1100, 650)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        for title, widget in self._build_tabs():
            self.tabs.addTab(widget, title)
        self.tabs.currentChanged.connect(self._refresh_current)
        self._refresh_current()

        self._build_menu()
        who = user.role.value + (f": {user.name}" if user.name else "")
        self.statusBar().showMessage(
            f"Пользователь — {who}   |   "
            f"БД: PostgreSQL {engine.url.host}:{engine.url.port}/{engine.url.database}"
        )

    def _build_tabs(self) -> list[tuple[str, QWidget]]:
        f = self.session_factory
        user = self.user
        if user.role == Role.ADMIN:
            tabs: list[tuple[str, QWidget]] = [
                (spec.title, EntityTab(spec, f))
                for spec in (
                    specs.STUDENTS,
                    specs.TEACHERS,
                    specs.COURSES,
                    specs.CLASSROOMS,
                    specs.GROUPS,
                    specs.ENROLLMENTS,
                    specs.PAYMENTS,
                    specs.LESSONS,
                )
            ]
            tabs.append(("Отчёты", ReportsTab(f)))
            return tabs

        read_only = {"can_add": False, "can_edit": False, "can_delete": False}
        if user.role == Role.TEACHER:
            tid = user.person_id

            def own_groups(q: Select) -> Select:
                return q.where(Group.teacher_id == tid)

            def own_lessons(q: Select) -> Select:
                return q.join(Group).where(Group.teacher_id == tid)

            def own_enrollments(q: Select) -> Select:
                return q.join(Group).where(Group.teacher_id == tid)

            return [
                (
                    "Моё расписание",
                    EntityTab(
                        specs.LESSONS,
                        f,
                        scope=own_lessons,
                        fk_scopes={"group_id": own_groups},
                    ),
                ),
                (
                    "Мои группы",
                    EntityTab(specs.GROUPS, f, scope=own_groups, **read_only),
                ),
                (
                    "Слушатели групп",
                    EntityTab(specs.ENROLLMENTS, f, scope=own_enrollments, **read_only),
                ),
            ]

        sid = user.person_id

        def my_lessons(q: Select) -> Select:
            return (
                q.join(Group)
                .join(Enrollment)
                .where(
                    Enrollment.student_id == sid,
                    Enrollment.status == EnrollmentStatus.ACTIVE,
                )
            )

        def my_enrollments(q: Select) -> Select:
            return q.where(Enrollment.student_id == sid)

        def my_payments(q: Select) -> Select:
            return q.join(Enrollment).where(Enrollment.student_id == sid)

        return [
            (
                "Моё расписание",
                EntityTab(specs.LESSONS, f, scope=my_lessons, **read_only),
            ),
            (
                "Мои курсы",
                EntityTab(specs.ENROLLMENTS, f, scope=my_enrollments, **read_only),
            ),
            (
                "Мои оплаты",
                EntityTab(specs.PAYMENTS, f, scope=my_payments, **read_only),
            ),
            ("Каталог курсов", EntityTab(specs.COURSES, f, **read_only)),
        ]

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Файл")
        if self.user.role == Role.ADMIN:
            act = QAction("Резервная копия БД…", self)
            act.setShortcut(QKeySequence("Ctrl+B"))
            act.triggered.connect(self._backup)
            file_menu.addAction(act)
        act = QAction("Обновить", self)
        act.setShortcut(QKeySequence.StandardKey.Refresh)
        act.triggered.connect(self._refresh_current)
        file_menu.addAction(act)
        file_menu.addSeparator()
        act = QAction("Сменить пользователя", self)
        act.triggered.connect(self._switch_user)
        file_menu.addAction(act)
        act = QAction("Выход", self)
        act.setShortcut(QKeySequence.StandardKey.Quit)
        act.triggered.connect(self.close)
        file_menu.addAction(act)

        help_menu = self.menuBar().addMenu("&Справка")
        act = QAction("О программе", self)
        act.triggered.connect(self._about)
        help_menu.addAction(act)

    def _refresh_current(self, *_: object) -> None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, (EntityTab, ReportsTab)):
            widget.refresh()

    def _backup(self) -> None:
        name = f"italian_school_backup_{dt.datetime.now():%Y%m%d_%H%M%S}.sql"
        path, _ = QFileDialog.getSaveFileName(
            self, "Резервная копия БД", name, "SQL-скрипт (*.sql)"
        )
        if not path:
            return
        try:
            backup(self.engine, path)
        except Exception as exc:  # noqa: BLE001 — показываем любую ошибку пользователю
            QMessageBox.critical(
                self, "Резервная копия", f"Не удалось создать копию:\n{exc}"
            )
            return
        QMessageBox.information(
            self,
            "Резервная копия",
            f"Копия БД сохранена:\n{path}\n\nВосстановление: psql -f <файл>",
        )

    def _switch_user(self) -> None:
        self.switch_user = True
        self.close()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "О программе",
            "<b>ИС «Школа изучения итальянского языка»</b><br>"
            "Вариант 9, лабораторные работы № 1–9.<br><br>"
            "Справочники: слушатели, преподаватели, курсы A1–C2, аудитории.<br>"
            "Журналы: группы, зачисления, оплаты, расписание.<br>"
            "Отчёты, роли пользователей, резервное копирование.<br><br>"
            "PyQt6 + SQLAlchemy + PostgreSQL.",
        )
