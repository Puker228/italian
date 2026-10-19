"""Описание справочников и журналов: поля форм, столбцы таблиц, бизнес-проверки."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from italian.models import (
    Classroom,
    Course,
    Enrollment,
    EnrollmentStatus,
    Group,
    Lesson,
    Level,
    Payment,
    Student,
    Teacher,
)
from italian.ui.widgets import Column, EntitySpec, Field, check_email, check_phone, fmt


def _validate_group(
    session: Session, obj: Group | None, v: dict[str, Any]
) -> str | None:
    query = select(Group.id).where(Group.name == v["name"])
    if obj is not None:
        query = query.where(Group.id != obj.id)
    if session.scalar(query) is not None:
        return f"Группа «{v['name']}» уже существует."
    return None


def _validate_enrollment(
    session: Session, obj: Enrollment | None, v: dict[str, Any]
) -> str | None:
    query = select(Enrollment.id).where(
        Enrollment.student_id == v["student_id"], Enrollment.group_id == v["group_id"]
    )
    if obj is not None:
        query = query.where(Enrollment.id != obj.id)
    if session.scalar(query) is not None:
        return "Этот слушатель уже зачислен в выбранную группу."
    group = session.get(Group, v["group_id"])
    if v["enroll_date"] > group.start_date + dt.timedelta(days=30):
        return (
            f"Набор в группу «{group}» закрыт: зачисление возможно не позднее "
            f"30 дней после старта ({group.start_date:%d.%m.%Y})."
        )
    return None


def _validate_payment(
    session: Session, obj: Payment | None, v: dict[str, Any]
) -> str | None:
    enrollment = session.get(Enrollment, v["enrollment_id"])
    debt = enrollment.get_debt()
    if obj is not None and obj.enrollment_id == enrollment.id:
        debt += obj.amount
    if v["amount"] > debt:
        return (
            f"Сумма превышает остаток к оплате по зачислению «{enrollment}»: "
            f"{fmt(debt)} ₽."
        )
    if v["pay_date"] < enrollment.enroll_date:
        return "Дата оплаты не может быть раньше даты зачисления."
    return None


def _validate_lesson(
    session: Session, obj: Lesson | None, v: dict[str, Any]
) -> str | None:
    group = session.get(Group, v["group_id"])
    room = session.get(Classroom, v["room_id"])
    exclude = obj.id if obj is not None else None
    if v["lesson_date"] < group.start_date:
        return f"Группа «{group}» начинает обучение {group.start_date:%d.%m.%Y}."
    if not room.is_free(v["lesson_date"], v["start_time"], exclude):
        return f"Аудитория {room.number} в это время уже занята."
    busy = session.scalar(
        select(Lesson)
        .join(Group)
        .where(
            Group.teacher_id == group.teacher_id,
            Lesson.lesson_date == v["lesson_date"],
            Lesson.start_time == v["start_time"],
            Lesson.id != (exclude or -1),
        )
    )
    if busy is not None:
        return f"Преподаватель {group.teacher} в это время ведёт занятие в группе «{busy.group}»."
    students = len(group.get_students())
    if students > room.capacity:
        return f"В аудитории {room.number} {room.capacity} мест, а в группе {students} слушателей."
    return None


STUDENTS = EntitySpec(
    model=Student,
    title="Слушатели",
    singular="слушатель",
    order_by=Student.last_name,
    fields=[
        Field("last_name", "Фамилия"),
        Field("first_name", "Имя"),
        Field("phone", "Телефон", required=False, validator=check_phone),
        Field("email", "E-mail", required=False, validator=check_email),
        Field("birth_date", "Дата рождения", "date", required=False),
    ],
    columns=[
        Column("Код", lambda o: o.id),
        Column("ФИО", lambda o: o.get_full_name()),
        Column("Телефон", lambda o: o.phone),
        Column("E-mail", lambda o: o.email),
        Column("Дата рождения", lambda o: o.birth_date),
        Column(
            "Групп",
            lambda o: sum(e.status == EnrollmentStatus.ACTIVE for e in o.enrollments),
        ),
        Column("Долг, ₽", lambda o: o.get_debt()),
    ],
)

TEACHERS = EntitySpec(
    model=Teacher,
    title="Преподаватели",
    singular="преподаватель",
    order_by=Teacher.last_name,
    fields=[
        Field("last_name", "Фамилия"),
        Field("first_name", "Имя"),
        Field("phone", "Телефон", required=False, validator=check_phone),
        Field("is_native", "Носитель языка", "bool"),
    ],
    columns=[
        Column("Код", lambda o: o.id),
        Column("ФИО", lambda o: o.get_full_name()),
        Column("Телефон", lambda o: o.phone),
        Column("Носитель языка", lambda o: o.is_native),
        Column("Групп", lambda o: len(o.groups)),
    ],
)

COURSES = EntitySpec(
    model=Course,
    title="Курсы",
    singular="курс",
    order_by=Course.level,
    fields=[
        Field("title", "Название"),
        Field("level", "Уровень", "enum", options=Level),
        Field("hours", "Часов", "int", minimum=1, maximum=1000),
        Field("price", "Стоимость", "money"),
    ],
    defaults={"hours": 48, "level": Level.A1},
    columns=[
        Column("Код", lambda o: o.id),
        Column("Название", lambda o: o.title),
        Column("Уровень", lambda o: o.level),
        Column("Часов", lambda o: o.hours),
        Column("Стоимость, ₽", lambda o: o.price),
        Column("Групп", lambda o: len(o.groups)),
    ],
)

CLASSROOMS = EntitySpec(
    model=Classroom,
    title="Аудитории",
    singular="аудитория",
    order_by=Classroom.number,
    fields=[
        Field("number", "Номер"),
        Field("capacity", "Вместимость", "int", minimum=1, maximum=200),
    ],
    defaults={"capacity": 10},
    columns=[
        Column("Код", lambda o: o.id),
        Column("Номер", lambda o: o.number),
        Column("Вместимость", lambda o: o.capacity),
        Column("Занятий", lambda o: len(o.lessons)),
    ],
)

GROUPS = EntitySpec(
    model=Group,
    title="Группы",
    singular="группа",
    order_by=Group.name,
    validate=_validate_group,
    fields=[
        Field("name", "Название"),
        Field("course_id", "Курс", "fk", options=Course),
        Field("teacher_id", "Преподаватель", "fk", options=Teacher),
        Field("start_date", "Дата старта", "date"),
    ],
    columns=[
        Column("Код", lambda o: o.id),
        Column("Название", lambda o: o.name),
        Column("Курс", lambda o: o.course),
        Column("Преподаватель", lambda o: o.teacher),
        Column("Дата старта", lambda o: o.start_date),
        Column("Слушателей", lambda o: len(o.get_students())),
        Column("Занятий", lambda o: len(o.lessons)),
    ],
)

ENROLLMENTS = EntitySpec(
    model=Enrollment,
    title="Зачисления",
    singular="зачисление",
    order_by=Enrollment.enroll_date.desc(),
    validate=_validate_enrollment,
    fields=[
        Field("student_id", "Слушатель", "fk", options=Student),
        Field("group_id", "Группа", "fk", options=Group),
        Field("enroll_date", "Дата зачисления", "date"),
        Field("status", "Статус", "enum", options=EnrollmentStatus),
    ],
    defaults={"status": EnrollmentStatus.ACTIVE},
    columns=[
        Column("Код", lambda o: o.id),
        Column("Слушатель", lambda o: o.student),
        Column("Группа", lambda o: o.group),
        Column("Курс", lambda o: o.group.course),
        Column("Дата", lambda o: o.enroll_date),
        Column("Статус", lambda o: o.status),
        Column("Стоимость, ₽", lambda o: o.group.course.price),
        Column("Оплачено, ₽", lambda o: o.get_paid()),
        Column("Долг, ₽", lambda o: o.get_debt()),
    ],
)

PAYMENTS = EntitySpec(
    model=Payment,
    title="Оплаты",
    singular="оплата",
    order_by=Payment.pay_date.desc(),
    validate=_validate_payment,
    fields=[
        Field("enrollment_id", "Зачисление", "fk", options=Enrollment),
        Field("pay_date", "Дата оплаты", "date"),
        Field("amount", "Сумма", "money"),
    ],
    columns=[
        Column("Код", lambda o: o.id),
        Column("Дата", lambda o: o.pay_date),
        Column("Слушатель", lambda o: o.enrollment.student),
        Column("Группа", lambda o: o.enrollment.group),
        Column("Сумма, ₽", lambda o: o.amount),
    ],
)

LESSONS = EntitySpec(
    model=Lesson,
    title="Расписание",
    singular="занятие",
    order_by=(Lesson.lesson_date, Lesson.start_time),
    validate=_validate_lesson,
    fields=[
        Field("group_id", "Группа", "fk", options=Group),
        Field("room_id", "Аудитория", "fk", options=Classroom),
        Field("lesson_date", "Дата", "date"),
        Field("start_time", "Время начала", "time"),
        Field("topic", "Тема", required=False),
    ],
    columns=[
        Column("Код", lambda o: o.id),
        Column("Дата", lambda o: o.lesson_date),
        Column("Время", lambda o: o.start_time),
        Column("Группа", lambda o: o.group),
        Column("Уровень", lambda o: o.group.course.level),
        Column("Преподаватель", lambda o: o.group.teacher),
        Column("Аудитория", lambda o: o.classroom.number),
        Column("Тема", lambda o: o.topic),
    ],
)
