"""Представления: главная, универсальный CRUD по реестру сущностей, отчёты, бэкап, API."""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from school.entities import ENTITIES, Entity
from school.formatting import fmt, is_number
from school.forms import ReportForm, form_class
from school.models import Course, Enrollment, EnrollmentStatus, Lesson, Payment, Student
from school.reports import REPORTS
from school.roles import Role, get_role


def _require_role(request: HttpRequest, *roles: Role) -> Role:
    role = get_role(request.user)
    if role is None or (roles and role not in roles):
        raise PermissionDenied("Недостаточно прав.")
    return role


def _entity(request: HttpRequest, slug: str, edit: bool = False) -> tuple[Entity, Role]:
    entity = ENTITIES.get(slug)
    if entity is None:
        raise Http404
    role = _require_role(request)
    access = entity.access.get(role)
    if access is None or (edit and not access.can_edit):
        raise PermissionDenied("Недостаточно прав.")
    return entity, role


@login_required
def home(request: HttpRequest) -> HttpResponse:
    role = _require_role(request)
    today = timezone.localdate()
    lessons = Lesson.objects.filter(lesson_date__gte=today).select_related(
        "group__teacher", "room"
    )
    context: dict[str, Any] = {"today": today}
    if role == Role.ADMIN:
        active = Enrollment.objects.filter(
            status=EnrollmentStatus.ACTIVE
        ).select_related("group__course")
        context["stats"] = [
            ("Учеников", Student.objects.count()),
            ("Курсов", Course.objects.count()),
            ("Активных зачислений", active.count()),
            ("Задолженность, ₽", fmt(sum((e.get_debt() for e in active), Decimal(0)))),
        ]
        month_start = today.replace(day=1)
        income = Payment.objects.filter(pay_date__gte=month_start)
        context["stats"].append(
            ("Поступило за месяц, ₽", fmt(sum((p.amount for p in income), Decimal(0))))
        )
    elif role == Role.TEACHER:
        lessons = lessons.filter(group__teacher=request.user.teacher)
    else:
        student = request.user.student
        lessons = lessons.filter(
            group__enrollments__student=student,
            group__enrollments__status=EnrollmentStatus.ACTIVE,
        )
        context["debt"] = fmt(student.get_debt()) if student.get_debt() else ""
    context["lessons"] = lessons.distinct()[:10]
    return render(request, "school/home.html", context)


@login_required
def entity_list(request: HttpRequest, slug: str) -> HttpResponse:
    entity, role = _entity(request, slug)
    qs = entity.queryset(role, request.user)
    query = request.GET.get("q", "").strip()
    if query:
        condition = Q()
        for lookup in entity.search:
            condition |= Q(**{f"{lookup}__icontains": query})
        qs = qs.filter(condition)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    rows = []
    for obj in page:
        values = [getter(obj) for _, getter in entity.columns]
        rows.append((obj, [(fmt(v), is_number(v)) for v in values]))
    return render(
        request,
        "school/list.html",
        {
            "entity": entity,
            "title": entity.title_for(role),
            "headers": [label for label, _ in entity.columns],
            "rows": rows,
            "page": page,
            "query": query,
            "can_edit": entity.access[role].can_edit,
        },
    )


def _save_form(request: HttpRequest, slug: str, pk: int | None) -> HttpResponse:
    entity, role = _entity(request, slug, edit=True)
    obj = get_object_or_404(entity.queryset(role, request.user), pk=pk) if pk else None
    Form = form_class(entity, role, request.user)
    form = Form(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        verb = "изменена" if obj else "добавлена"
        messages.success(request, f"Запись «{saved}» {verb}.")
        return redirect("entity_list", slug=slug)
    return render(
        request,
        "school/form.html",
        {
            "entity": entity,
            "title": entity.title_for(role),
            "form": form,
            "object": obj,
        },
    )


@login_required
def entity_create(request: HttpRequest, slug: str) -> HttpResponse:
    return _save_form(request, slug, None)


@login_required
def entity_update(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    return _save_form(request, slug, pk)


@login_required
def entity_delete(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    entity, role = _entity(request, slug, edit=True)
    obj = get_object_or_404(entity.queryset(role, request.user), pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Нельзя удалить «{obj}»: на запись ссылаются другие данные "
                "(группы, зачисления, занятия). Сначала удалите или измените их.",
            )
        else:
            messages.success(request, f"Запись «{obj}» удалена.")
        return redirect("entity_list", slug=slug)
    return render(
        request,
        "school/confirm_delete.html",
        {"entity": entity, "title": entity.title_for(role), "object": obj},
    )


@login_required
def reports(request: HttpRequest) -> HttpResponse:
    _require_role(request, Role.ADMIN)
    today = timezone.localdate()
    initial = {
        "kind": "debtors",
        "start": today.replace(month=1, day=1),
        "end": today + dt.timedelta(days=30),
    }
    choices = [(key, title) for key, (title, _) in REPORTS.items()]
    form = ReportForm(request.GET or initial, choices=choices)
    context: dict[str, Any] = {"form": form}
    if form.is_valid():
        title, build = REPORTS[form.cleaned_data["kind"]]
        header, rows, summary = build(
            form.cleaned_data["start"], form.cleaned_data["end"]
        )
        if request.GET.get("format") == "csv":
            return _csv_response(title, header, rows, summary)
        context.update(
            title=title,
            header=header,
            rows=[[(fmt(v), is_number(v)) for v in row] for row in rows],
            summary=summary,
        )
    return render(request, "school/reports.html", context)


def _csv_response(
    title: str, header: list[str], rows: list[list[Any]], summary: str
) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(title)}.csv"
    response.write("﻿")  # BOM, чтобы Excel распознал UTF-8
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    for row in rows:
        writer.writerow(fmt(v) for v in row)
    writer.writerow([summary])
    return response


@login_required
def backup(request: HttpRequest) -> HttpResponse:
    """Резервная копия данных (ТЗ: надёжность). Восстановление: manage.py loaddata <файл>."""
    _require_role(request, Role.ADMIN)
    buffer = io.StringIO()
    call_command("dumpdata", "auth.user", "school", indent=2, stdout=buffer)
    name = f"italian_school_{timezone.localtime():%Y%m%d_%H%M%S}.json"
    response = HttpResponse(buffer.getvalue(), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


@login_required
def api_schedule(request: HttpRequest) -> JsonResponse:
    """REST API (ЛР 8): расписание текущего пользователя в JSON."""
    role = _require_role(request)
    entity = ENTITIES["lessons"]
    qs = entity.queryset(role, request.user)
    if date_from := request.GET.get("from"):
        qs = qs.filter(lesson_date__gte=date_from)
    data = [
        {
            "id": les.id,
            "date": les.lesson_date.isoformat(),
            "time": les.start_time.strftime("%H:%M"),
            "group": les.group.name,
            "level": les.group.course.level,
            "teacher": str(les.group.teacher),
            "room": les.room.number,
            "topic": les.topic,
        }
        for les in qs
    ]
    return JsonResponse(
        {"count": len(data), "results": data}, json_dumps_params={"ensure_ascii": False}
    )


@login_required
def api_courses(request: HttpRequest) -> JsonResponse:
    _require_role(request)
    data = [
        {
            "id": c.id,
            "title": c.title,
            "level": c.level,
            "hours": c.hours,
            "price": str(c.price),
        }
        for c in Course.objects.all()
    ]
    return JsonResponse(
        {"count": len(data), "results": data}, json_dumps_params={"ensure_ascii": False}
    )
