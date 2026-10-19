"""Реестр сущностей: какие поля в форме, какие столбцы в таблице и кому что доступно.

По этому описанию одни и те же представления (views.py) строят список,
форму добавления/изменения и удаление для всех восьми таблиц.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Model, QuerySet

from school.models import (
    Classroom,
    Course,
    Enrollment,
    EnrollmentStatus,
    Group,
    Lesson,
    Payment,
    Student,
    Teacher,
)
from school.roles import Role

Scope = Callable[[QuerySet, Any], QuerySet]


def everything(qs: QuerySet, user: Any) -> QuerySet:
    return qs


@dataclass
class Access:
    scope: Scope = everything  # какие записи видит роль
    can_edit: bool = False  # может ли добавлять, изменять, удалять
    title: str | None = None  # своё название раздела для роли
    # Ограничение выпадающих списков формы: {поле: функция(queryset, user)}
    choices: dict[str, Scope] = field(default_factory=dict)


@dataclass
class Entity:
    slug: str
    model: type[Model]
    title: str
    fields: list[str]
    columns: list[tuple[str, Callable[[Any], Any]]]
    search: list[str]
    access: dict[Role, Access]
    select_related: list[str] = field(default_factory=list)

    @property
    def singular(self) -> str:
        return str(self.model._meta.verbose_name)

    def title_for(self, role: Role | None) -> str:
        access = self.access.get(role) if role else None
        return (access and access.title) or self.title

    def queryset(self, role: Role, user: Any) -> QuerySet:
        qs = self.model.objects.select_related(*self.select_related)
        return self.access[role].scope(qs, user).distinct()


ADMIN = {Role.ADMIN: Access(can_edit=True)}


def own_groups(qs: QuerySet, user: Any) -> QuerySet:
    return qs.filter(teacher=user.teacher)


def teacher_lessons(qs: QuerySet, user: Any) -> QuerySet:
    return qs.filter(group__teacher=user.teacher)


def teacher_enrollments(qs: QuerySet, user: Any) -> QuerySet:
    return qs.filter(group__teacher=user.teacher)


def student_lessons(qs: QuerySet, user: Any) -> QuerySet:
    return qs.filter(
        group__enrollments__student=user.student,
        group__enrollments__status=EnrollmentStatus.ACTIVE,
    )


def student_enrollments(qs: QuerySet, user: Any) -> QuerySet:
    return qs.filter(student=user.student)


def student_payments(qs: QuerySet, user: Any) -> QuerySet:
    return qs.filter(enrollment__student=user.student)


ENTITY_LIST = [
    Entity(
        slug="students",
        model=Student,
        title="Ученики",
        fields=["last_name", "first_name", "phone", "email", "birth_date", "user"],
        columns=[
            ("Код", lambda o: o.id),
            ("ФИО", lambda o: o.get_full_name()),
            ("Телефон", lambda o: o.phone),
            ("E-mail", lambda o: o.email),
            ("Дата рождения", lambda o: o.birth_date),
            ("Долг, ₽", lambda o: o.get_debt()),
        ],
        search=["last_name", "first_name", "phone", "email"],
        access=ADMIN,
    ),
    Entity(
        slug="teachers",
        model=Teacher,
        title="Преподаватели",
        fields=["last_name", "first_name", "phone", "is_native", "user"],
        columns=[
            ("Код", lambda o: o.id),
            ("ФИО", lambda o: o.get_full_name()),
            ("Телефон", lambda o: o.phone),
            ("Носитель языка", lambda o: o.is_native),
            ("Групп", lambda o: o.groups.count()),
        ],
        search=["last_name", "first_name", "phone"],
        access=ADMIN,
    ),
    Entity(
        slug="courses",
        model=Course,
        title="Курсы",
        fields=["title", "level", "hours", "price"],
        columns=[
            ("Код", lambda o: o.id),
            ("Название", lambda o: o.title),
            ("Уровень", lambda o: o.level),
            ("Часов", lambda o: o.hours),
            ("Стоимость, ₽", lambda o: o.price),
            ("Групп", lambda o: o.groups.count()),
        ],
        search=["title", "level"],
        access={
            Role.ADMIN: Access(can_edit=True),
            Role.STUDENT: Access(title="Каталог курсов"),
        },
    ),
    Entity(
        slug="classrooms",
        model=Classroom,
        title="Аудитории",
        fields=["number", "capacity"],
        columns=[
            ("Код", lambda o: o.id),
            ("Номер", lambda o: o.number),
            ("Вместимость", lambda o: o.capacity),
            ("Занятий", lambda o: o.lessons.count()),
        ],
        search=["number"],
        access=ADMIN,
    ),
    Entity(
        slug="groups",
        model=Group,
        title="Группы",
        fields=["name", "course", "teacher", "start_date"],
        columns=[
            ("Код", lambda o: o.id),
            ("Название", lambda o: o.name),
            ("Курс", lambda o: o.course),
            ("Преподаватель", lambda o: o.teacher),
            ("Дата старта", lambda o: o.start_date),
            ("Учеников", lambda o: o.get_students().count()),
            ("Занятий", lambda o: o.lessons.count()),
        ],
        search=["name", "course__title", "teacher__last_name"],
        select_related=["course", "teacher"],
        access={
            Role.ADMIN: Access(can_edit=True),
            Role.TEACHER: Access(scope=own_groups, title="Мои группы"),
        },
    ),
    Entity(
        slug="enrollments",
        model=Enrollment,
        title="Зачисления",
        fields=["student", "group", "enroll_date", "status"],
        columns=[
            ("Код", lambda o: o.id),
            ("Ученик", lambda o: o.student),
            ("Группа", lambda o: o.group),
            ("Курс", lambda o: o.group.course),
            ("Дата", lambda o: o.enroll_date),
            ("Статус", lambda o: o.get_status_display()),
            ("Стоимость, ₽", lambda o: o.group.course.price),
            ("Оплачено, ₽", lambda o: o.get_paid()),
            ("Долг, ₽", lambda o: o.get_debt()),
        ],
        search=["student__last_name", "student__first_name", "group__name", "status"],
        select_related=["student", "group__course"],
        access={
            Role.ADMIN: Access(can_edit=True),
            Role.TEACHER: Access(scope=teacher_enrollments, title="Ученики групп"),
            Role.STUDENT: Access(scope=student_enrollments, title="Мои курсы"),
        },
    ),
    Entity(
        slug="payments",
        model=Payment,
        title="Оплаты",
        fields=["enrollment", "pay_date", "amount"],
        columns=[
            ("Код", lambda o: o.id),
            ("Дата", lambda o: o.pay_date),
            ("Ученик", lambda o: o.enrollment.student),
            ("Группа", lambda o: o.enrollment.group),
            ("Сумма, ₽", lambda o: o.amount),
        ],
        search=["enrollment__student__last_name", "enrollment__group__name"],
        select_related=["enrollment__student", "enrollment__group"],
        access={
            Role.ADMIN: Access(can_edit=True),
            Role.STUDENT: Access(scope=student_payments, title="Мои оплаты"),
        },
    ),
    Entity(
        slug="lessons",
        model=Lesson,
        title="Расписание",
        fields=["group", "room", "lesson_date", "start_time", "topic"],
        columns=[
            ("Код", lambda o: o.id),
            ("Дата", lambda o: o.lesson_date),
            ("Время", lambda o: o.start_time),
            ("Группа", lambda o: o.group),
            ("Уровень", lambda o: o.group.course.level),
            ("Преподаватель", lambda o: o.group.teacher),
            ("Аудитория", lambda o: o.room.number),
            ("Тема", lambda o: o.topic),
        ],
        search=["group__name", "topic", "room__number", "group__teacher__last_name"],
        select_related=["group__course", "group__teacher", "room"],
        access={
            Role.ADMIN: Access(can_edit=True),
            Role.TEACHER: Access(
                scope=teacher_lessons,
                can_edit=True,
                title="Моё расписание",
                choices={"group": own_groups},
            ),
            Role.STUDENT: Access(scope=student_lessons, title="Моё расписание"),
        },
    ),
]

ENTITIES = {e.slug: e for e in ENTITY_LIST}
