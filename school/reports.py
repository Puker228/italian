"""Отчёты: должники, поступления, наполняемость групп, нагрузка преподавателей, расписание."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q

from school.formatting import fmt
from school.models import Enrollment, EnrollmentStatus, Group, Lesson, Payment, Teacher

Report = tuple[list[str], list[list[Any]], str]


def debtors(start: dt.date, end: dt.date) -> Report:
    rows, total = [], Decimal(0)
    active = Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE).select_related(
        "student", "group__course"
    )
    for e in active:
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
    header = ["Ученик", "Телефон", "Группа", "Стоимость, ₽", "Оплачено, ₽", "Долг, ₽"]
    return header, rows, f"Должников: {len(rows)}, общая задолженность: {fmt(total)} ₽"


def income(start: dt.date, end: dt.date) -> Report:
    payments = (
        Payment.objects.filter(pay_date__range=(start, end))
        .select_related("enrollment__student", "enrollment__group")
        .order_by("pay_date", "id")
    )
    rows = [
        [p.pay_date, p.enrollment.student, p.enrollment.group, p.amount]
        for p in payments
    ]
    total = sum((r[-1] for r in rows), Decimal(0))
    return (
        ["Дата", "Ученик", "Группа", "Сумма, ₽"],
        rows,
        f"Платежей: {len(rows)}, поступило: {fmt(total)} ₽",
    )


def group_fill(start: dt.date, end: dt.date) -> Report:
    groups = Group.objects.select_related("course", "teacher").annotate(
        students=Count(
            "enrollments",
            filter=Q(enrollments__status=EnrollmentStatus.ACTIVE),
            distinct=True,
        ),
        period_lessons=Count(
            "lessons", filter=Q(lessons__lesson_date__range=(start, end)), distinct=True
        ),
    )
    rows = [
        [g, g.course, g.teacher, g.start_date, g.students, g.period_lessons]
        for g in groups
    ]
    return (
        ["Группа", "Курс", "Преподаватель", "Старт", "Учеников", "Занятий за период"],
        rows,
        f"Групп: {len(rows)}, учеников: {sum(r[4] for r in rows)}",
    )


def teacher_load(start: dt.date, end: dt.date) -> Report:
    teachers = Teacher.objects.annotate(
        group_count=Count("groups", distinct=True),
        period_lessons=Count(
            "groups__lessons",
            filter=Q(groups__lessons__lesson_date__range=(start, end)),
            distinct=True,
        ),
    )
    rows = [[t, t.is_native, t.group_count, t.period_lessons] for t in teachers]
    return (
        ["Преподаватель", "Носитель языка", "Групп", "Занятий за период"],
        rows,
        f"Всего занятий за период: {sum(r[3] for r in rows)}",
    )


def schedule(start: dt.date, end: dt.date) -> Report:
    lessons = Lesson.objects.filter(lesson_date__range=(start, end)).select_related(
        "group__teacher", "room"
    )
    rows = [
        [
            les.lesson_date,
            les.start_time,
            les.group,
            les.group.teacher,
            les.room.number,
            les.topic,
        ]
        for les in lessons
    ]
    return (
        ["Дата", "Время", "Группа", "Преподаватель", "Аудитория", "Тема"],
        rows,
        f"Занятий: {len(rows)}",
    )


REPORTS: dict[str, tuple[str, Callable[[dt.date, dt.date], Report]]] = {
    "debtors": ("Должники по оплате", debtors),
    "income": ("Поступления оплат за период", income),
    "groups": ("Наполняемость групп", group_fill),
    "teachers": ("Нагрузка преподавателей", teacher_load),
    "schedule": ("Расписание на период", schedule),
}
